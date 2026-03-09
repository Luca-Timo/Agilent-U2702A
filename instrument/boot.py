"""
U2702A USB Firmware Boot Module

The U2702A powers up in firmware-update mode (PID 0x2818) and requires
a sequence of vendor-specific USB control transfers to transition into
normal USBTMC operation mode (PID 0x2918).

Boot sequence reverse-engineered from python-usbtmc (issue #31) and
Wireshark captures of the Agilent IO Libraries Windows driver.

Reference: https://github.com/python-ivi/python-usbtmc/issues/31
"""

import os
import time
import logging

import usb.core
import usb.util

logger = logging.getLogger(__name__)

_MACOS_PERMISSION_HINT = (
    "macOS blocks raw USB access for unprivileged processes.\n"
    "Fix:\n"
    "  1. Run with sudo:  sudo {venv}/bin/python test_connection.py\n"
    "  2. On Apple Silicon laptops, also check:\n"
    "     System Settings > Privacy & Security > Allow accessories to connect\n"
    "     Set to 'Always Allow', then unplug and re-plug the device."
)

# Agilent/Keysight vendor ID
VID_AGILENT = 0x0957

# U2702A product IDs
PID_BOOT = 0x2818      # Firmware update mode (device powers up here)
PID_OPERATIONAL = 0x2918  # Normal USBTMC mode (after boot sequence)

# Boot sequence: 6 vendor-specific control transfers
# Transfers 1-5: read firmware info from internal registers (device-to-host)
# Transfer 6: send boot command (host-to-device)
_BOOT_SEQUENCE = [
    # (bmRequestType, bRequest, wValue, wIndex, data_or_wLength)
    (0xC0, 0x0C, 0x0000, 0x047E, 0x0001),   # Read 1 byte
    (0xC0, 0x0C, 0x0000, 0x047D, 0x0006),   # Read 6 bytes
    (0xC0, 0x0C, 0x0000, 0x0484, 0x0005),   # Read 5 bytes (U2701A/U2702A)
    (0xC0, 0x0C, 0x0000, 0x0472, 0x000C),   # Read 12 bytes
    (0xC0, 0x0C, 0x0000, 0x047A, 0x0001),   # Read 1 byte
    (0x40, 0x0C, 0x0000, 0x0475,            # Write 8 bytes: BOOT COMMAND
     b'\x00\x00\x01\x01\x00\x00\x08\x01'),
]

# Re-enumeration polling
_POLL_INTERVAL_S = 0.5
_POLL_MAX_ATTEMPTS = 40  # 40 * 0.5s = 20s max wait


def find_device(vid, pid, serial=None):
    """Find a USB device by VID/PID and optional serial number.

    Uses find(find_all=True) and manual filtering to avoid pyusb's
    default behavior of opening the device during find() — which
    hangs on macOS for devices that can't be opened without root.

    Args:
        vid: USB vendor ID.
        pid: USB product ID.
        serial: Optional serial number string to match.

    Returns:
        usb.core.Device or None.
    """
    devices = usb.core.find(find_all=True, idVendor=vid, idProduct=pid)
    for dev in devices:
        if serial is None:
            return dev
        # Serial comparison requires opening the device, which may fail
        try:
            dev_serial = usb.util.get_string(dev, dev.iSerialNumber)
            if dev_serial == serial:
                return dev
        except Exception:
            # Can't read serial — return the device anyway if it matches VID/PID
            return dev
    return None


def get_serial(device):
    """Read the serial number from a USB device.

    Args:
        device: usb.core.Device instance.

    Returns:
        Serial number string, or None if unavailable.
    """
    try:
        return usb.util.get_string(device, device.iSerialNumber)
    except Exception as e:
        logger.warning("Could not read serial number: %s", e)
        return None


def is_boot_mode(device):
    """Check if a device is in firmware-update (boot) mode.

    Args:
        device: usb.core.Device instance.

    Returns:
        True if the device has PID_BOOT.
    """
    return device.idProduct == PID_BOOT


def boot_device(device=None):
    """Execute the firmware boot sequence on a U2702A in boot mode.

    If no device is provided, searches for one automatically. If the
    device is already in operational mode (PID 0x2918), returns it
    immediately.

    Args:
        device: Optional usb.core.Device in boot mode (PID 0x2818).

    Returns:
        usb.core.Device in operational mode (PID 0x2918).

    Raises:
        RuntimeError: If no device found or boot sequence fails.
    """
    # Auto-detect device if not provided
    if device is None:
        device = find_device(VID_AGILENT, PID_BOOT)
        if device is None:
            # Maybe already in operational mode?
            device = find_device(VID_AGILENT, PID_OPERATIONAL)
            if device is not None:
                logger.info(
                    "Device already in operational mode (PID 0x%04X)",
                    PID_OPERATIONAL,
                )
                return device
            raise RuntimeError(
                "No U2702A found. Check USB connection. "
                f"Expected VID=0x{VID_AGILENT:04X}, "
                f"PID=0x{PID_BOOT:04X} or 0x{PID_OPERATIONAL:04X}"
            )

    # If already operational, nothing to do
    if not is_boot_mode(device):
        logger.info("Device already operational (PID 0x%04X)", device.idProduct)
        return device

    logger.info(
        "Device found in boot mode (PID 0x%04X). Starting firmware boot...",
        PID_BOOT,
    )

    # Capture serial number before boot (needed to re-find after re-enumeration)
    serial = get_serial(device)
    logger.info("Device serial: %s", serial)

    # Detach kernel driver if attached (macOS may claim the device)
    try:
        if device.is_kernel_driver_active(0):
            device.detach_kernel_driver(0)
            logger.debug("Detached kernel driver from interface 0")
    except (usb.core.USBError, NotImplementedError) as e:
        logger.debug("Kernel driver detach: %s", e)

    # Set configuration (required on macOS before control transfers)
    try:
        device.set_configuration()
        logger.debug("USB configuration set")
    except usb.core.USBError as e:
        logger.debug("Set configuration: %s", e)

    # Send the 6-step boot sequence
    for i, transfer in enumerate(_BOOT_SEQUENCE):
        bmRequestType, bRequest, wValue, wIndex, data_or_wLength = transfer
        try:
            result = device.ctrl_transfer(
                bmRequestType, bRequest, wValue, wIndex, data_or_wLength,
                timeout=5000,
            )
            if bmRequestType & 0x80:  # Device-to-host (read)
                logger.debug(
                    "Boot step %d: READ wIndex=0x%04X -> %s",
                    i + 1, wIndex, bytes(result).hex(),
                )
            else:  # Host-to-device (write)
                logger.debug(
                    "Boot step %d: WRITE wIndex=0x%04X, %d bytes",
                    i + 1, wIndex, len(data_or_wLength),
                )
        except usb.core.USBError as e:
            import sys
            venv = os.path.dirname(os.path.dirname(sys.executable))
            # Detect macOS permission errors: "Other error", no errno,
            # or timeout on the very first transfer (common on macOS
            # when the process lacks USB entitlements)
            err_str = str(e)
            is_permission = (
                "Other error" in err_str
                or e.errno is None
                or (i == 0 and "timed out" in err_str.lower())
            )
            if is_permission:
                raise PermissionError(
                    f"Cannot access USB device (boot step {i + 1}).\n"
                    + _MACOS_PERMISSION_HINT.format(venv=venv)
                ) from e
            raise RuntimeError(
                f"Boot sequence failed at step {i + 1} "
                f"(wIndex=0x{wIndex:04X}): {e}"
            ) from e

    logger.info("Boot sequence sent. Waiting for device to re-enumerate...")

    # Release the boot-mode device handle
    usb.util.dispose_resources(device)
    del device

    # Poll for the device to re-appear with the operational PID
    for attempt in range(_POLL_MAX_ATTEMPTS):
        time.sleep(_POLL_INTERVAL_S)
        new_device = find_device(VID_AGILENT, PID_OPERATIONAL, serial)
        if new_device is not None:
            logger.info(
                "Device re-enumerated as PID 0x%04X after %.1fs",
                PID_OPERATIONAL,
                (attempt + 1) * _POLL_INTERVAL_S,
            )
            return new_device

    raise RuntimeError(
        f"Device did not re-enumerate as PID 0x{PID_OPERATIONAL:04X} "
        f"within {_POLL_MAX_ATTEMPTS * _POLL_INTERVAL_S:.0f}s. "
        "Try unplugging and re-plugging the USB cable."
    )


def find_and_boot():
    """Convenience function: find a U2702A and ensure it's in operational mode.

    Handles both cases:
    - Device in boot mode -> runs boot sequence -> returns operational device
    - Device already operational -> returns immediately

    Returns:
        usb.core.Device in operational mode.

    Raises:
        RuntimeError: If no device found or boot fails.
    """
    return boot_device()
