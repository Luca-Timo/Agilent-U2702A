"""
Serial Bridge Client for ESP32-S3 USB Bridge.

Communicates with the ESP32-S3 firmware over UART to send SCPI commands
to the U2702A oscilloscope and receive responses.

Protocol (firmware serial_bridge.c):
  TX (Mac -> ESP32): "SCPI_COMMAND\\n"
  RX text response:  "response_data\\n"
  RX set command OK: "OK\\n"
  RX binary data:    '#' + 4-byte LE uint32 length + raw payload
  RX status:         "!STATUS:READY\\n", "!STATUS:WAITING\\n", etc.
  RX errors:         "!ERROR:QUERY_FAILED\\n", etc.

Usage:
    from instrument.serial_bridge import SerialBridge

    bridge = SerialBridge("/dev/cu.usbserial-110", baudrate=2000000)
    bridge.open()
    print(bridge.query("*IDN?"))
    bridge.write(":RUN")
    data = bridge.query_binary("WAV:DATA?")
    bridge.close()

Thread-safe: all public methods acquire an internal lock. Can be used
from any thread. For async/GUI use, see SerialBridgeWorker (QObject).
"""

import struct
import threading
import time
from collections import deque
from typing import Optional, Callable

import serial
import serial.tools.list_ports


# --- Constants ---

DEFAULT_BAUDRATE = 2_000_000
DEFAULT_TIMEOUT_S = 5.0
BINARY_MARKER = ord('#')

# Bridge status values
STATUS_READY = "READY"
STATUS_WAITING = "WAITING"
STATUS_BOOTING = "BOOTING"
STATUS_DISCONNECTED = "DISCONNECTED"


class SerialBridgeError(Exception):
    """Base exception for serial bridge errors."""
    pass


class BridgeTimeoutError(SerialBridgeError):
    """Command timed out waiting for response."""
    pass


class BridgeProtocolError(SerialBridgeError):
    """Unexpected data from bridge."""
    pass


class BridgeCommandError(SerialBridgeError):
    """Bridge reported an error (e.g., QUERY_FAILED)."""
    pass


# --- Port Discovery ---

def list_serial_ports():
    """List available serial ports, CP2102N ports first.

    Returns:
        List of (device_path, description) tuples.
    """
    ports = serial.tools.list_ports.comports()
    # CP2102N: VID 0x10C4, PID 0xEA60
    cp2102n = [p for p in ports if p.vid == 0x10C4 and p.pid == 0xEA60]
    others = [p for p in ports if p not in cp2102n]
    return [(p.device, f"{p.description} [{p.device}]") for p in cp2102n + others]


# --- Synchronous Bridge Client ---

class SerialBridge:
    """Synchronous serial bridge client.

    Thread-safe: all public methods use an internal lock.
    Suitable for scripting, testing, and as the backend for GUI workers.
    """

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE,
                 timeout: float = DEFAULT_TIMEOUT_S,
                 on_status: Optional[Callable[[str], None]] = None):
        """
        Args:
            port: Serial port path (e.g., "/dev/cu.usbserial-110").
            baudrate: Baud rate (default 2000000 to match firmware).
            timeout: Default response timeout in seconds.
            on_status: Optional callback for bridge status changes.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.on_status = on_status

        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()
        self._bridge_status = STATUS_DISCONNECTED
        self._buffer = bytearray()

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def bridge_status(self) -> str:
        return self._bridge_status

    def open(self):
        """Open the serial port."""
        with self._lock:
            if self.is_open:
                return
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.05,  # Short read timeout for responsive parsing
                write_timeout=1.0,
            )
            self._buffer.clear()
            self._bridge_status = STATUS_DISCONNECTED

    def close(self):
        """Close the serial port."""
        with self._lock:
            if self._serial:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            self._bridge_status = STATUS_DISCONNECTED
            self._buffer.clear()

    def write(self, command: str, timeout: Optional[float] = None) -> str:
        """Send a set command and wait for OK response.

        Args:
            command: SCPI command string (e.g., ":RUN").
            timeout: Override default timeout.

        Returns:
            Response string (typically "OK").

        Raises:
            BridgeTimeoutError: No response within timeout.
            BridgeCommandError: Bridge reported an error.
        """
        return self._send_and_receive(command, timeout or self.timeout,
                                       expect_binary=False)

    def query(self, command: str, timeout: Optional[float] = None) -> str:
        """Send a query and return the text response.

        Args:
            command: SCPI query string (e.g., "*IDN?").
            timeout: Override default timeout.

        Returns:
            Response string.

        Raises:
            BridgeTimeoutError: No response within timeout.
            BridgeCommandError: Bridge reported an error.
        """
        return self._send_and_receive(command, timeout or self.timeout,
                                       expect_binary=False)

    def query_binary(self, command: str,
                     timeout: Optional[float] = None) -> bytes:
        """Send a query and return binary response data.

        Use for WAV:DATA? and similar binary-response commands.
        The firmware strips the IEEE 488.2 header and sends raw payload
        with a 4-byte LE length prefix after '#'.

        Args:
            command: SCPI query (e.g., "WAV:DATA?").
            timeout: Override default timeout.

        Returns:
            Raw binary payload bytes.

        Raises:
            BridgeTimeoutError: No response within timeout.
            BridgeCommandError: Bridge reported an error.
        """
        return self._send_and_receive(command, timeout or self.timeout,
                                       expect_binary=True)

    def wait_for_status(self, target: str = STATUS_READY,
                        timeout: float = 30.0) -> str:
        """Wait for a specific bridge status.

        Reads from the serial port until the target status is received
        or timeout expires. Useful after connecting to wait for READY.

        Args:
            target: Status string to wait for (default: "READY").
            timeout: Maximum wait time in seconds.

        Returns:
            The status string received.

        Raises:
            BridgeTimeoutError: Status not received within timeout.
        """
        deadline = time.monotonic() + timeout
        with self._lock:
            while time.monotonic() < deadline:
                self._read_and_buffer()
                # Check for status lines in buffer
                while b'\n' in self._buffer:
                    line = self._consume_line()
                    if line.startswith("!STATUS:"):
                        status = line[8:]
                        self._update_status(status)
                        if status == target:
                            return status
                    # Discard other lines while waiting
        raise BridgeTimeoutError(
            f"Timed out waiting for status '{target}' "
            f"(last: '{self._bridge_status}')"
        )

    # --- Internal Methods ---

    def _send_and_receive(self, command: str, timeout: float,
                          expect_binary: bool):
        """Send command and wait for response (text or binary)."""
        with self._lock:
            if not self.is_open:
                raise SerialBridgeError("Serial port not open")

            # Flush any stale data in buffers
            self._drain_status_messages()

            # Send command
            cmd_bytes = (command + "\n").encode("utf-8")
            self._serial.write(cmd_bytes)

            # Wait for response
            deadline = time.monotonic() + timeout

            while time.monotonic() < deadline:
                self._read_and_buffer()

                if len(self._buffer) == 0:
                    continue

                # Check first byte to determine response type
                first_byte = self._buffer[0]

                if first_byte == BINARY_MARKER:
                    # Binary response: '#' + 4-byte LE length + payload
                    if len(self._buffer) < 5:
                        continue  # Need more data
                    payload_len = struct.unpack_from('<I', self._buffer, 1)[0]
                    total_needed = 5 + payload_len
                    if len(self._buffer) < total_needed:
                        # Stay in the main loop — _read_and_buffer()
                        # will accumulate more bytes each iteration.
                        continue

                    payload = bytes(self._buffer[5:total_needed])
                    del self._buffer[:total_needed]
                    if expect_binary:
                        return payload
                    else:
                        # Got binary but expected text — return hex summary
                        return f"[BINARY {len(payload)} bytes]"

                elif first_byte == ord('!'):
                    # Status or error message — read until newline
                    if b'\n' not in self._buffer:
                        continue
                    line = self._consume_line()
                    if line.startswith("!STATUS:"):
                        self._update_status(line[8:])
                        continue  # Not a response to our command
                    elif line.startswith("!ERROR:"):
                        error_msg = line[7:]
                        raise BridgeCommandError(
                            f"Bridge error: {error_msg}"
                        )
                    else:
                        # Unknown ! message, treat as text
                        return line

                else:
                    # Text response — read until newline
                    if b'\n' not in self._buffer:
                        continue
                    line = self._consume_line()
                    if expect_binary:
                        raise BridgeProtocolError(
                            f"Expected binary response, got text: {line}"
                        )
                    return line

            raise BridgeTimeoutError(
                f"Timeout waiting for response to '{command}'"
            )

    def _read_and_buffer(self):
        """Read available bytes into the internal buffer."""
        if not self._serial:
            return
        waiting = self._serial.in_waiting
        if waiting > 0:
            data = self._serial.read(waiting)
            self._buffer.extend(data)
        else:
            # Block briefly for at least 1 byte
            data = self._serial.read(1)
            if data:
                self._buffer.extend(data)
                # Grab any bytes that arrived during the blocking read
                waiting = self._serial.in_waiting
                if waiting > 0:
                    more = self._serial.read(waiting)
                    self._buffer.extend(more)

    def _read_exact(self, count: int, timeout: float) -> Optional[bytes]:
        """Read exactly `count` bytes with timeout."""
        deadline = time.monotonic() + timeout
        data = bytearray()
        while len(data) < count:
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                return None
            old_timeout = self._serial.timeout
            self._serial.timeout = min(remaining_time, 0.1)
            chunk = self._serial.read(count - len(data))
            self._serial.timeout = old_timeout
            if chunk:
                data.extend(chunk)
        return bytes(data)

    def _consume_line(self) -> str:
        """Consume and return the first newline-terminated line from buffer."""
        idx = self._buffer.index(b'\n')
        line = self._buffer[:idx].decode("utf-8", errors="replace").strip()
        del self._buffer[:idx + 1]
        return line

    def _drain_status_messages(self):
        """Read and process any pending status messages before sending."""
        if not self._serial:
            return
        # Read whatever is available
        while self._serial.in_waiting > 0:
            data = self._serial.read(self._serial.in_waiting)
            self._buffer.extend(data)
        # Process complete lines
        while b'\n' in self._buffer:
            # Peek at the line
            idx = self._buffer.index(b'\n')
            line = self._buffer[:idx].decode("utf-8", errors="replace").strip()
            if line.startswith("!STATUS:"):
                del self._buffer[:idx + 1]
                self._update_status(line[8:])
            elif line.startswith("!ERROR:"):
                del self._buffer[:idx + 1]
                # Discard stale errors
            else:
                # Non-status data — might be a stale response; discard
                del self._buffer[:idx + 1]

    def _update_status(self, status: str):
        """Update bridge status and invoke callback."""
        self._bridge_status = status
        if self.on_status:
            try:
                self.on_status(status)
            except Exception:
                pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self):
        state = "open" if self.is_open else "closed"
        return (f"SerialBridge(port={self.port!r}, baud={self.baudrate}, "
                f"state={state}, status={self._bridge_status!r})")
