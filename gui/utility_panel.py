"""
Utility panel — Autoscale, measurement bar toggle, future function placeholders.

Sits at the top of the right sidebar, above HORIZONTAL / TRIGGER / VERTICAL.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QPushButton, QLabel, QFrame,
)

from gui.theme import ACCENT_BLUE, TEXT_SECONDARY


class UtilityPanel(QGroupBox):
    """Utility controls — Autoscale, measurement toggle, future placeholders.

    Signals:
        autoscale_requested() — user clicked Autoscale button
        measurement_bar_toggled(bool) — user toggled measurement bar visibility
    """

    autoscale_requested = Signal()
    measurement_bar_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__("UTILITY", parent)
        self._meas_visible = True
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # --- Autoscale button ---
        self._autoscale_btn = QPushButton("⟳ Autoscale")
        self._autoscale_btn.setFixedHeight(36)
        self._autoscale_btn.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white; "
            f"font-weight: bold; font-size: 12px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: #5aafff; }}"
            f"QPushButton:disabled {{ background-color: #333333; color: #666666; }}"
        )
        self._autoscale_btn.clicked.connect(self._on_autoscale)
        layout.addWidget(self._autoscale_btn)

        # --- Measurement bar toggle ---
        self._meas_btn = QPushButton("Measurements: ON")
        self._meas_btn.setFixedHeight(28)
        self._meas_btn.setCheckable(True)
        self._meas_btn.setChecked(True)
        self._meas_btn.setStyleSheet(
            "QPushButton { font-size: 11px; }"
        )
        self._meas_btn.clicked.connect(self._on_meas_toggled)
        layout.addWidget(self._meas_btn)

        # --- Separator ---
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #333333;")
        layout.addWidget(separator)

        # --- Future measurements placeholder ---
        placeholder = QLabel("Cursors, Rise/Fall — coming in v0.4.x")
        placeholder.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; font-style: italic;"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        layout.addWidget(placeholder)

    def _on_autoscale(self):
        self.autoscale_requested.emit()

    def _on_meas_toggled(self):
        self._meas_visible = self._meas_btn.isChecked()
        text = "ON" if self._meas_visible else "OFF"
        self._meas_btn.setText(f"Measurements: {text}")
        self.measurement_bar_toggled.emit(self._meas_visible)

    # --- Public API ---

    def set_autoscale_enabled(self, enabled: bool):
        """Enable/disable the autoscale button (e.g., when not connected)."""
        self._autoscale_btn.setEnabled(enabled)
