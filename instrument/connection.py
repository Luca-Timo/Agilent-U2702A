"""
U2702A Connection Manager

Handles device discovery, firmware boot, and VISA session management.
Uses pyvisa with pyvisa-py backend (no NI-VISA required).

Workflow:
    1. Check if device is in boot mode (PID 0x2818) -> run boot sequence
    2. Open VISA resource via pyvisa-py
    3. Apply macOS race-condition workaround (0.5s delay after reset)
    4. Send initialization sequence
    5. Ready for SCPI communication
"""

import time
import logging

import pyvisa
import usb.core

from instrument.boot import (
    VID_AGILENT,
    PID_BOOT,
    PID_OPERATIONAL,
    find_and_boot,
    find_device,
    get_serial,
)

logger = logging.getLogger(__name__)

# VISA resource string template for USB instruments
_VISA_RESOURCE_TEMPLATE = "USB0::0x{vid:04X}::0x{pid:04X}::{serial}::0::INSTR"

# Default VISA timeout (ms) — generous for slow commands
DEFAULT_TIMEOUT_MS = 5000

# macOS pyvisa-py race condition workaround delay (seconds)
# See: https://github.com/pyvisa/pyvisa-py/issues/308
_MACOS_USB_SETTLE_DELAY_S = 0.5


class ConnectionManager:
    """Manages the USB connection to a U2702A oscilloscope.

    Handles firmware boot, VISA session lifecycle, and provides
    a clean interface for sending SCPI commands.

    Usage:
        mgr = ConnectionManager()
        mgr.connect()
        print(mgr.query("*IDN?"))
        mgr.disconnect()

    Or as a context manager:
        with ConnectionManager() as mgr:
            print(mgr.query("*IDN?"))
    """

    def __init__(self, timeout_ms=DEFAULT_TIMEOUT_MS):
        """Initialize the connection manager.

        Args:
            timeout_ms: VISA I/O timeout in milliseconds.
        """
        self._timeout_ms = timeout_ms
        self._rm = None        # pyvisa ResourceManager
        self._session = None   # pyvisa Resource (instrument session)
        self._serial = None    # Device serial number
        self._idn = None       # Cached *IDN? response

    # --- Properties ---

    @property
    def is_connected(self):
        """True if a VISA session is open."""
        return self._session is not None

    @property
    def serial(self):
        """Device serial number (available after connect)."""
        return self._serial

    @property
    def idn(self):
        """Cached *IDN? response (available after connect)."""
        return self._idn

    @property
    def resource_name(self):
        """VISA resource string (available after connect)."""
        if self._session is not None:
            return self._session.resource_name
        return None

    # --- Connection lifecycle ---

    def connect(self):
        """Connect to the U2702A.

        1. Boots device if in firmware-update mode
        2. Opens VISA session via pyvisa-py
        3. Sends *IDN? to verify communication

        Raises:
            RuntimeError: If device not found or connection fails.
        """
        if self.is_connected:
            logger.warning("Already connected. Disconnect first.")
            return

        logger.info("Connecting to U2702A...")

        # Step 1: Ensure device is in operational mode
        usb_device = self._ensure_operational()

        # Capture serial before VISA takes over
        self._serial = get_serial(usb_device)
        logger.info("Device serial: %s", self._serial)

        # Release pyusb handle so pyvisa-py can claim the device
        usb.util.dispose_resources(usb_device)
        del usb_device

        # macOS settle delay — let the USB stack stabilize
        time.sleep(_MACOS_USB_SETTLE_DELAY_S)

        # Step 2: Open VISA session
        self._open_visa_session()

        # Step 3: Verify communication
        self._verify_connection()

        logger.info("Connected: %s", self._idn)

    def disconnect(self):
        """Close the VISA session and release resources."""
        if self._session is not None:
            try:
                self._session.close()
                logger.info("VISA session closed.")
            except Exception as e:
                logger.warning("Error closing session: %s", e)
            self._session = None

        if self._rm is not None:
            try:
                self._rm.close()
            except Exception:
                pass
            self._rm = None

        self._idn = None
        logger.info("Disconnected.")

    # --- SCPI I/O ---

    def write(self, command):
        """Send a SCPI command (no response expected).

        Args:
            command: SCPI command string.

        Raises:
            RuntimeError: If not connected.
        """
        self._check_connected()
        logger.debug("WRITE: %s", command)
        self._session.write(command)

    def query(self, command):
        """Send a SCPI query and return the response string.

        Args:
            command: SCPI query string (should end with '?').

        Returns:
            Response string (stripped of whitespace).

        Raises:
            RuntimeError: If not connected.
        """
        self._check_connected()
        logger.debug("QUERY: %s", command)
        response = self._session.query(command).strip()
        logger.debug("  -> %s", response)
        return response

    def query_binary(self, command):
        """Send a SCPI query and return raw binary response bytes.

        Used for WAV:DATA? which returns IEEE 488.2 binary blocks.

        Args:
            command: SCPI query string.

        Returns:
            Raw bytes from the instrument.

        Raises:
            RuntimeError: If not connected.
        """
        self._check_connected()
        logger.debug("QUERY_BINARY: %s", command)
        self._session.write(command)
        raw = self._session.read_raw()
        logger.debug("  -> %d bytes", len(raw))
        return raw

    # --- Context manager ---

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    # --- Internal helpers ---

    def _ensure_operational(self):
        """Make sure the device is in operational USBTMC mode.

        Checks for operational device first. If device is in boot mode,
        waits briefly for the launchd daemon to boot it. If the daemon
        doesn't handle it, attempts to boot directly (requires root).

        Returns:
            usb.core.Device in operational mode.

        Raises:
            RuntimeError: If device not found or boot fails.
        """
        # Check for operational device first (fast path — daemon already booted)
        device = find_device(VID_AGILENT, PID_OPERATIONAL)
        if device is not None:
            logger.info("Device already in operational mode.")
            return device

        # Check for boot-mode device
        device = find_device(VID_AGILENT, PID_BOOT)
        if device is not None:
            logger.info(
                "Device in boot mode (PID 0x%04X). "
                "Waiting for boot daemon...", PID_BOOT,
            )
            usb.util.dispose_resources(device)

            # Wait for the launchd daemon to boot it (up to 10s)
            for attempt in range(20):
                import time as _time
                _time.sleep(0.5)
                op_device = find_device(VID_AGILENT, PID_OPERATIONAL)
                if op_device is not None:
                    logger.info(
                        "Device booted by daemon after %.1fs",
                        (attempt + 1) * 0.5,
                    )
                    return op_device

            # Daemon didn't boot it — try direct boot (needs root)
            logger.warning("Boot daemon did not respond. Trying direct boot...")
            try:
                return find_and_boot()
            except PermissionError:
                raise RuntimeError(
                    "Device is in boot mode (PID 0x2818) but the boot daemon "
                    "is not installed. Install it with:\n"
                    "  sudo python3 daemon/install_daemon.py\n"
                    "Then unplug and re-plug the oscilloscope."
                )

        raise RuntimeError(
            "No U2702A found on USB. Check connection. "
            f"Expected VID=0x{VID_AGILENT:04X}, "
            f"PID=0x{PID_BOOT:04X} (boot) or "
            f"0x{PID_OPERATIONAL:04X} (operational)"
        )

    def _open_visa_session(self):
        """Open a pyvisa session to the device."""
        # Use pyvisa-py backend explicitly
        self._rm = pyvisa.ResourceManager("@py")

        # Build resource string
        resource = _VISA_RESOURCE_TEMPLATE.format(
            vid=VID_AGILENT,
            pid=PID_OPERATIONAL,
            serial=self._serial or "",
        )
        logger.info("Opening VISA resource: %s", resource)

        try:
            self._session = self._rm.open_resource(resource)
        except pyvisa.errors.VisaIOError:
            # Fallback: list all USB resources and try to find our device
            logger.warning(
                "Direct resource open failed. Scanning for USB instruments..."
            )
            resources = self._rm.list_resources("USB?*INSTR")
            logger.info("Found resources: %s", resources)

            target = None
            for res in resources:
                if f"0x{PID_OPERATIONAL:04X}" in res.upper() or \
                   f"0x{PID_OPERATIONAL:04x}" in res.lower() or \
                   f"::{PID_OPERATIONAL}::" in res:
                    target = res
                    break

            if target is None:
                raise RuntimeError(
                    "Could not open VISA session. "
                    f"No USB resource matching PID 0x{PID_OPERATIONAL:04X}. "
                    f"Available: {resources}"
                )

            logger.info("Using discovered resource: %s", target)
            self._session = self._rm.open_resource(target)

        # Configure session
        self._session.timeout = self._timeout_ms

        # Set termination characters for text queries
        # Binary reads (WAV:DATA?) use read_raw() which ignores these
        self._session.read_termination = "\n"
        self._session.write_termination = "\n"

        logger.info("VISA session opened successfully.")

    def _verify_connection(self):
        """Send *IDN? and verify we're talking to a U2702A."""
        try:
            self._idn = self.query("*IDN?")
        except Exception as e:
            self.disconnect()
            raise RuntimeError(f"Device did not respond to *IDN?: {e}") from e

        if "U2702A" not in self._idn and "U2701A" not in self._idn:
            logger.warning(
                "Unexpected device identity: %s (expected U2702A)", self._idn
            )

    def _check_connected(self):
        """Raise if not connected."""
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
