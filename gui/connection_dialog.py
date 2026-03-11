"""
Connection dialog — separate window for selecting and connecting to a device.

Opens on startup or from File > Connect. Shows available serial ports,
auto-detects CP2102N, and establishes the serial bridge connection.
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QGridLayout, QFrame, QTextEdit,
    QSizePolicy,
)
from PySide6.QtGui import QFont

from instrument.serial_bridge import (
    SerialBridge, list_serial_ports, DEFAULT_BAUDRATE,
    BridgeTimeoutError, SerialBridgeError,
)
from instrument.demo_bridge import DemoBridge


class ConnectionDialog(QDialog):
    """Device connection dialog.

    Signals:
        connection_established(SerialBridge) — emitted when connected
    """

    connection_established = Signal(object)  # SerialBridge

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Oscilloscope")
        self.setMinimumSize(480, 340)
        self.resize(500, 380)
        self.setModal(True)

        self._bridge: Optional[SerialBridge] = None
        self._connecting = False

        self._setup_ui()
        self._refresh_ports()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # --- Header ---
        header = QLabel("Connect to Agilent U2702A")
        header.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e0e0e0; "
            "padding: 4px 0;"
        )
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        subtitle = QLabel("via ESP32-S3 USB Bridge (CP2102N)")
        subtitle.setStyleSheet("color: #888888; font-size: 11px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444444;")
        layout.addWidget(sep)

        # --- Device selection ---
        device_group = QGroupBox("Device")
        device_layout = QGridLayout()

        device_layout.addWidget(QLabel("Port:"), 0, 0)
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(280)
        device_layout.addWidget(self._port_combo, 0, 1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self._refresh_ports)
        device_layout.addWidget(self._refresh_btn, 0, 2)

        device_layout.addWidget(QLabel("Baud:"), 1, 0)
        self._baud_combo = QComboBox()
        self._baud_combo.addItems(["2000000", "1000000", "921600", "115200"])
        self._baud_combo.setCurrentIndex(0)
        device_layout.addWidget(self._baud_combo, 1, 1)

        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # --- Status log ---
        self._status_log = QTextEdit()
        self._status_log.setReadOnly(True)
        self._status_log.setMaximumHeight(100)
        font = QFont("Menlo", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._status_log.setFont(font)
        self._status_log.setStyleSheet(
            "QTextEdit { background-color: #1a1a1a; color: #888888; "
            "border: 1px solid #333333; border-radius: 3px; }"
        )
        layout.addWidget(self._status_log)

        # --- Buttons ---
        btn_layout = QHBoxLayout()

        self._demo_btn = QPushButton("Demo Signal")
        self._demo_btn.setFixedWidth(120)
        self._demo_btn.setFixedHeight(36)
        self._demo_btn.setStyleSheet(
            "QPushButton { background-color: #50c878; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #60d888; }"
            "QPushButton:pressed { background-color: #40b868; }"
        )
        self._demo_btn.clicked.connect(self._on_demo)
        btn_layout.addWidget(self._demo_btn)

        btn_layout.addStretch()

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedWidth(120)
        self._connect_btn.setFixedHeight(36)
        self._connect_btn.setStyleSheet(
            "QPushButton { background-color: #4a9eff; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #5ab0ff; }"
            "QPushButton:pressed { background-color: #3a8eee; }"
            "QPushButton:disabled { background-color: #333333; color: #666666; }"
        )
        self._connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self._connect_btn)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(80)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

    def _refresh_ports(self):
        """Populate the port dropdown with available serial ports."""
        self._port_combo.clear()
        ports = list_serial_ports()

        if ports:
            cp2102n_found = False
            for device, description in ports:
                self._port_combo.addItem(description, device)
                if "CP2102" in description or "usbserial" in device:
                    cp2102n_found = True

            if cp2102n_found:
                self._log("CP2102N bridge detected", "#50c878")
            else:
                self._log("No CP2102N found — showing all ports", "#ffcc00")
        else:
            self._port_combo.addItem("No serial ports found", "")
            self._log("No serial ports found", "#ff5555")

    def _log(self, text: str, color: str = "#888888"):
        """Append a line to the status log."""
        self._status_log.append(
            f'<span style="color: {color};">{text}</span>'
        )

    def _on_demo(self):
        """Connect with a synthetic demo signal generator."""
        self._log("Starting demo signal generator...", "#50c878")
        bridge = DemoBridge()
        bridge.open()
        self._bridge = bridge
        self._log("Demo signal ready (1 kHz 3.3 V PWM)", "#50c878")
        self.connection_established.emit(bridge)
        self.accept()

    def _on_connect(self):
        """Handle connect button click."""
        port = self._port_combo.currentData()
        if not port:
            self._log("No port selected", "#ff5555")
            return

        baud = int(self._baud_combo.currentText())
        self._connecting = True
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting...")
        self._log(f"Connecting to {port} @ {baud} baud...")

        # Use a timer to keep UI responsive
        QTimer.singleShot(100, lambda: self._do_connect(port, baud))

    def _do_connect(self, port: str, baud: int):
        """Perform the actual connection (runs after brief UI update)."""
        try:
            bridge = SerialBridge(port, baudrate=baud)
            bridge.open()
            self._log("Port opened, waiting for bridge status...", "#ffcc00")

            # Wait for READY status
            try:
                status = bridge.wait_for_status(timeout=5.0)
                self._log(f"Bridge status: {status}", "#50c878")
            except BridgeTimeoutError:
                self._log("No status received — assuming connected", "#ffcc00")

            self._bridge = bridge
            self._log("Connected!", "#50c878")

            # Emit signal and close
            self.connection_established.emit(bridge)
            self.accept()

        except Exception as e:
            self._log(f"Connection failed: {e}", "#ff5555")
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("Connect")
            self._connecting = False

    def get_bridge(self) -> Optional[SerialBridge]:
        """Get the established bridge (after dialog accepted)."""
        return self._bridge

    def closeEvent(self, event):
        """Clean up if dialog closed without connecting."""
        if self._bridge and not self.result():
            self._bridge.close()
            self._bridge = None
        super().closeEvent(event)
