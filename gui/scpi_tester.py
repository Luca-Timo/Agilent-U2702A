"""
SCPI Tester GUI for U2702A via ESP32-S3 Serial Bridge.

A lightweight PySide6 tool for sending SCPI commands to the oscilloscope
through the ESP32-S3 USB bridge and viewing responses.

Usage:
    python gui/scpi_tester.py
    python -m gui.scpi_tester

Requires: PySide6, pyserial, numpy
"""

import sys
import os
import time
from datetime import datetime
from functools import partial
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, Signal, Slot, QObject, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QComboBox, QPushButton,
    QLineEdit, QPlainTextEdit, QSplitter, QSizePolicy,
)
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor, QAction

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from instrument.serial_bridge import (
    SerialBridge, list_serial_ports, DEFAULT_BAUDRATE,
    BridgeTimeoutError, BridgeCommandError, BridgeProtocolError,
    SerialBridgeError,
)
from instrument import protocol

# --- Quick Command Definitions ---

QUICK_COMMANDS = [
    ("System", [
        ("*IDN?", "*IDN?"),
        ("*CLS", "*CLS"),
        ("*OPC?", "*OPC?"),
    ]),
    ("Acquisition", [
        (":RUN", ":RUN"),
        (":STOP", ":STOP"),
        (":SINGLE", ":SINGLE"),
    ]),
    ("Channel 1", [
        ("Scale?", "CHANNEL1:SCALE?"),
        ("Offset?", "CHANNEL1:OFFSET?"),
        ("Coupling?", "CHANNEL1:COUPLING?"),
        ("Display?", "CHANNEL1:DISPLAY?"),
    ]),
    ("Channel 2", [
        ("Scale?", "CHANNEL2:SCALE?"),
        ("Offset?", "CHANNEL2:OFFSET?"),
        ("Coupling?", "CHANNEL2:COUPLING?"),
        ("Display?", "CHANNEL2:DISPLAY?"),
    ]),
    ("Timebase", [
        ("T/div?", "TIM:SCAL?"),
        ("Range?", "TIM:RANG?"),
        ("Position?", "TIMEBASE:POS?"),
        ("Mode?", "TIM:MODE?"),
    ]),
    ("Trigger", [
        ("Source?", "TRIGGER:EDGE:SOURCE?"),
        ("Level?", "TRIGGER:EDGE:LEVEL?"),
        ("Slope?", "TRIG:EDGE:SLOPE?"),
        ("Sweep?", "TRIGGER:SWEEP?"),
    ]),
    ("Waveform", [
        ("Src CH1", "WAV:SOUR CHAN1"),
        ("Src CH2", "WAV:SOUR CHAN2"),
        ("WAV:DATA?", "WAV:DATA?"),
    ]),
]


# --- Serial Worker (QObject on QThread) ---

class SerialWorker(QObject):
    """Handles serial I/O on a background thread."""

    # Signals to GUI
    text_response = Signal(str, str)    # (command, response)
    binary_response = Signal(str, bytes)  # (command, raw_data)
    status_changed = Signal(str)        # bridge status
    error_occurred = Signal(str)        # error message
    connected = Signal()
    disconnected = Signal()

    def __init__(self):
        super().__init__()
        self._bridge: Optional[SerialBridge] = None
        self._running = False

    @Slot(str, int)
    def connect_port(self, port: str, baudrate: int):
        """Open serial port and start listening for status."""
        try:
            self._bridge = SerialBridge(
                port, baudrate=baudrate,
                on_status=self._on_bridge_status,
            )
            self._bridge.open()
            self.connected.emit()

            # Try to get initial status
            try:
                status = self._bridge.wait_for_status(timeout=3.0)
                self.status_changed.emit(status)
            except BridgeTimeoutError:
                # Bridge might not send status unprompted — that's OK
                self.status_changed.emit("CONNECTED")

        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {e}")

    @Slot()
    def disconnect_port(self):
        """Close serial port."""
        if self._bridge:
            self._bridge.close()
            self._bridge = None
        self.status_changed.emit("DISCONNECTED")
        self.disconnected.emit()

    @Slot(str)
    def send_command(self, command: str):
        """Send a SCPI command and emit the response."""
        if not self._bridge or not self._bridge.is_open:
            self.error_occurred.emit("Not connected")
            return

        is_binary_query = command.strip().upper() == "WAV:DATA?"

        try:
            if is_binary_query:
                data = self._bridge.query_binary(command)
                self.binary_response.emit(command, data)
            elif command.strip().endswith("?"):
                response = self._bridge.query(command)
                self.text_response.emit(command, response)
            else:
                response = self._bridge.write(command)
                self.text_response.emit(command, response)

        except BridgeCommandError as e:
            self.error_occurred.emit(str(e))
            self.text_response.emit(command, f"ERROR: {e}")
        except BridgeTimeoutError as e:
            self.error_occurred.emit(str(e))
            self.text_response.emit(command, f"TIMEOUT: {e}")
        except BridgeProtocolError as e:
            self.error_occurred.emit(str(e))
            self.text_response.emit(command, f"PROTOCOL ERROR: {e}")
        except SerialBridgeError as e:
            self.error_occurred.emit(str(e))
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error: {e}")

    @Slot(list)
    def send_batch(self, commands: list):
        """Send a batch of commands sequentially."""
        for cmd in commands:
            self.send_command(cmd)
            QThread.msleep(30)  # Small delay between commands

    def _on_bridge_status(self, status: str):
        """Called from SerialBridge when status message received."""
        self.status_changed.emit(status)


# --- Log Widget ---

class LogWidget(QPlainTextEdit):
    """Formatted SCPI command/response log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(10000)
        font = QFont("Menlo", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _append_colored(self, text: str, color: str):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(text + "\n", fmt)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def log_command(self, cmd: str):
        self._append_colored(f"{self._timestamp()}  >>> {cmd}", "#4a9eff")

    def log_response(self, cmd: str, response: str):
        self._append_colored(f"{self._timestamp()}  <<< {response}", "#50c878")

    def log_binary(self, cmd: str, data: bytes):
        total = len(data)
        parts = [f"[BINARY] {total} bytes"]
        if total >= 2:
            parts.append(f"prefix: {data[0]:02X} {data[1]:02X}")
            adc = data[2:2 + 1256]
            if len(adc) > 0:
                arr = np.frombuffer(adc, dtype=np.uint8)
                parts.append(
                    f"ADC: {len(arr)} pts, "
                    f"min={arr.min()}, max={arr.max()}, "
                    f"mean={arr.mean():.1f}"
                )
        self._append_colored(
            f"{self._timestamp()}  <<< {', '.join(parts)}", "#b080ff"
        )

    def log_error(self, msg: str):
        self._append_colored(f"{self._timestamp()}  !!! {msg}", "#ff5555")

    def log_status(self, status: str):
        self._append_colored(
            f"{self._timestamp()}  --- Bridge: {status}", "#ffaa00"
        )

    def log_info(self, msg: str):
        self._append_colored(f"{self._timestamp()}  ... {msg}", "#888888")


# --- Command Input with History ---

class CommandInput(QLineEdit):
    """QLineEdit with Up/Down arrow command history."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._history_idx = -1
        self._draft = ""
        self.setPlaceholderText("Enter SCPI command (e.g., *IDN?)")

    def add_to_history(self, cmd: str):
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
            if len(self._history) > 200:
                self._history.pop(0)
        self._history_idx = -1
        self._draft = ""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            if not self._history:
                return
            if self._history_idx == -1:
                self._draft = self.text()
                self._history_idx = len(self._history) - 1
            elif self._history_idx > 0:
                self._history_idx -= 1
            self.setText(self._history[self._history_idx])
        elif event.key() == Qt.Key.Key_Down:
            if self._history_idx == -1:
                return
            if self._history_idx < len(self._history) - 1:
                self._history_idx += 1
                self.setText(self._history[self._history_idx])
            else:
                self._history_idx = -1
                self.setText(self._draft)
        else:
            super().keyPressEvent(event)


# --- Status Indicator ---

class StatusIndicator(QLabel):
    """Colored status dot + text."""

    COLORS = {
        "READY": "#50c878",
        "CONNECTED": "#50c878",
        "WAITING": "#ffcc00",
        "BOOTING": "#ffcc00",
        "DISCONNECTED": "#ff5555",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_status("DISCONNECTED")

    def set_status(self, status: str):
        color = self.COLORS.get(status, "#888888")
        self.setText(f" {status} ")
        self.setStyleSheet(
            f"background-color: {color}; color: white; "
            f"border-radius: 4px; padding: 2px 8px; "
            f"font-weight: bold; font-size: 11px;"
        )


# --- Main Window ---

class SCPITesterWindow(QMainWindow):
    """SCPI Tester main window.

    Can be used standalone or with a shared SerialBridge from the main window.
    When a bridge is provided, the connection bar is hidden and the shared
    bridge is used directly.
    """

    # Signals to worker (cross-thread)
    sig_connect = Signal(str, int)
    sig_disconnect = Signal()
    sig_send = Signal(str)
    sig_batch = Signal(list)

    def __init__(self, bridge=None):
        super().__init__()
        self.setWindowTitle("SCPI Tester - Agilent U2702A")
        self.setMinimumSize(700, 500)
        self.resize(850, 700)

        self._is_connected = False
        self._shared_bridge = bridge

        # Worker + thread
        self._worker = SerialWorker()
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._connect_signals()
        self._thread.start()

        # Build UI
        self._build_ui()

        if bridge and bridge.is_open:
            # Use shared bridge — auto-connect, hide connection bar
            self._conn_widget.setVisible(False)
            self._worker._bridge = bridge
            self._is_connected = True
            self._on_connected()
            self._on_status_changed("SHARED")
        else:
            self._refresh_ports()

    def _connect_signals(self):
        """Wire up signal/slot connections between GUI and worker."""
        # GUI -> Worker
        self.sig_connect.connect(self._worker.connect_port)
        self.sig_disconnect.connect(self._worker.disconnect_port)
        self.sig_send.connect(self._worker.send_command)
        self.sig_batch.connect(self._worker.send_batch)

        # Worker -> GUI
        self._worker.text_response.connect(self._on_text_response)
        self._worker.binary_response.connect(self._on_binary_response)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)

    def _build_ui(self):
        """Build the complete UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(6)

        # --- Connection bar (hidden when using shared bridge) ---
        self._conn_widget = QWidget()
        conn_layout = QHBoxLayout(self._conn_widget)
        conn_layout.setContentsMargins(0, 0, 0, 0)

        conn_layout.addWidget(QLabel("Port:"))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(250)
        conn_layout.addWidget(self._port_combo)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_ports)
        conn_layout.addWidget(self._refresh_btn)

        conn_layout.addWidget(QLabel("Baud:"))
        self._baud_combo = QComboBox()
        self._baud_combo.addItems(["2000000", "1000000", "921600", "115200"])
        self._baud_combo.setCurrentIndex(0)
        conn_layout.addWidget(self._baud_combo)

        conn_layout.addStretch()

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setMinimumWidth(100)
        self._connect_btn.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self._connect_btn)

        self._status_indicator = StatusIndicator()
        conn_layout.addWidget(self._status_indicator)

        layout.addWidget(self._conn_widget)

        # --- Quick command buttons ---
        btn_group = QGroupBox("Quick Commands")
        btn_grid = QGridLayout()
        btn_grid.setSpacing(4)

        row = 0
        for group_name, commands in QUICK_COMMANDS:
            label = QLabel(f"<b>{group_name}</b>")
            label.setAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)
            btn_grid.addWidget(label, row, 0)

            for col, (btn_text, scpi_cmd) in enumerate(commands, start=1):
                btn = QPushButton(btn_text)
                btn.setMaximumHeight(28)
                btn.setSizePolicy(QSizePolicy.Policy.Preferred,
                                  QSizePolicy.Policy.Fixed)
                btn.clicked.connect(partial(self._send_quick, scpi_cmd))
                btn_grid.addWidget(btn, row, col)
            row += 1

        # Init Sequence button on its own row
        label = QLabel("<b>Batch</b>")
        label.setAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
        btn_grid.addWidget(label, row, 0)
        init_btn = QPushButton("Init Sequence (42 cmds)")
        init_btn.clicked.connect(self._send_init_sequence)
        btn_grid.addWidget(init_btn, row, 1, 1, 3)

        btn_group.setLayout(btn_grid)
        layout.addWidget(btn_group)

        # --- Custom command input ---
        cmd_layout = QHBoxLayout()
        cmd_layout.addWidget(QLabel("Command:"))

        self._cmd_input = CommandInput()
        self._cmd_input.returnPressed.connect(self._send_custom)
        cmd_layout.addWidget(self._cmd_input)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_custom)
        cmd_layout.addWidget(send_btn)

        layout.addLayout(cmd_layout)

        # --- Log area ---
        self._log = LogWidget()
        layout.addWidget(self._log, stretch=1)

        # Clear button
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._log.clear)
        clear_layout.addWidget(clear_btn)
        layout.addLayout(clear_layout)

        # Status bar
        self.statusBar().showMessage("Disconnected")

    def _refresh_ports(self):
        """Populate the port dropdown."""
        self._port_combo.clear()
        ports = list_serial_ports()
        if ports:
            for device, description in ports:
                self._port_combo.addItem(description, device)
        else:
            self._port_combo.addItem("No ports found", "")

    def _toggle_connection(self):
        if self._is_connected:
            self.sig_disconnect.emit()
        else:
            port = self._port_combo.currentData()
            if not port:
                self._log.log_error("No serial port selected")
                return
            baud = int(self._baud_combo.currentText())
            self._log.log_info(f"Connecting to {port} @ {baud} baud...")
            self.sig_connect.emit(port, baud)

    def _send_quick(self, command: str):
        if not self._is_connected:
            self._log.log_error("Not connected")
            return
        self._log.log_command(command)
        self.sig_send.emit(command)

    def _send_custom(self):
        cmd = self._cmd_input.text().strip()
        if not cmd:
            return
        if not self._is_connected:
            self._log.log_error("Not connected")
            return
        self._cmd_input.add_to_history(cmd)
        self._cmd_input.clear()
        self._log.log_command(cmd)
        self.sig_send.emit(cmd)

    def _send_init_sequence(self):
        if not self._is_connected:
            self._log.log_error("Not connected")
            return
        self._log.log_info(
            f"Sending init sequence ({len(protocol.INIT_SEQUENCE)} commands)..."
        )
        for cmd in protocol.INIT_SEQUENCE:
            self._log.log_command(cmd)
        self.sig_batch.emit(list(protocol.INIT_SEQUENCE))

    # --- Worker response slots ---

    @Slot(str, str)
    def _on_text_response(self, cmd: str, response: str):
        self._log.log_response(cmd, response)

    @Slot(str, bytes)
    def _on_binary_response(self, cmd: str, data: bytes):
        self._log.log_binary(cmd, data)

    @Slot(str)
    def _on_status_changed(self, status: str):
        self._status_indicator.set_status(status)
        self._log.log_status(status)
        self.statusBar().showMessage(f"Bridge: {status}")

    @Slot(str)
    def _on_error(self, msg: str):
        self._log.log_error(msg)

    @Slot()
    def _on_connected(self):
        self._is_connected = True
        self._connect_btn.setText("Disconnect")
        self._port_combo.setEnabled(False)
        self._baud_combo.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        port = self._port_combo.currentData()
        baud = self._baud_combo.currentText()
        self.statusBar().showMessage(f"Connected: {port} @ {baud}")
        self._log.log_info(f"Connected to {port}")

    @Slot()
    def _on_disconnected(self):
        self._is_connected = False
        self._connect_btn.setText("Connect")
        self._port_combo.setEnabled(True)
        self._baud_combo.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        self.statusBar().showMessage("Disconnected")
        self._log.log_info("Disconnected")

    def closeEvent(self, event):
        """Clean shutdown: stop worker thread.

        When using shared bridge, do NOT disconnect — the main window owns it.
        """
        if self._is_connected and not self._shared_bridge:
            self.sig_disconnect.emit()
        self._thread.quit()
        self._thread.wait(2000)
        super().closeEvent(event)


# --- Entry Point ---

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = SCPITesterWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
