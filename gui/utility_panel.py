"""
Utility panel — Autoscale, measurement bar toggle, cursor controls.

Sits at the top of the right sidebar, above HORIZONTAL / TRIGGER / VERTICAL.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton

from gui.theme import ACCENT_BLUE


class UtilityPanel(QGroupBox):
    """Utility controls — Autoscale, measurement toggle, cursor mode.

    Signals:
        autoscale_requested() — user clicked Autoscale button
        measurement_bar_toggled(bool) — user toggled measurement bar visibility
        cursor_mode_changed(str) — cursor mode changed ("off"/"time"/"voltage"/"both")
    """

    autoscale_requested = Signal()
    measurement_bar_toggled = Signal(bool)
    cursor_mode_changed = Signal(str)
    cursor_reset_requested = Signal()
    dmm_mode_toggled = Signal(bool)

    # Carousel: Off → Both → X Only → Y Only → Off …
    _CURSOR_MODES = [
        ("off",      "Cursors: OFF"),
        ("both",     "Cursors: X+Y"),
        ("time",     "Cursors: X"),
        ("voltage",  "Cursors: Y"),
    ]

    def __init__(self, parent=None):
        super().__init__("UTILITY", parent)
        self._meas_visible = True
        self._cursor_idx = 0  # index into _CURSOR_MODES
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

        # --- DMM Mode toggle ---
        self._dmm_btn = QPushButton("DMM Mode: OFF")
        self._dmm_btn.setFixedHeight(28)
        self._dmm_btn.setCheckable(True)
        self._dmm_btn.setChecked(False)
        self._dmm_btn.setStyleSheet(
            "QPushButton { font-size: 11px; }"
        )
        self._dmm_btn.clicked.connect(self._on_dmm_toggled)
        layout.addWidget(self._dmm_btn)

        # --- Cursor row: carousel button + reset button ---
        cursor_row = QHBoxLayout()
        cursor_row.setSpacing(4)

        mode, label = self._CURSOR_MODES[0]
        self._cursor_btn = QPushButton(label)
        self._cursor_btn.setFixedHeight(28)
        self._cursor_btn.setStyleSheet(
            "QPushButton { font-size: 11px; }"
        )
        self._cursor_btn.clicked.connect(self._on_cursor_clicked)
        cursor_row.addWidget(self._cursor_btn)

        self._cursor_reset_btn = QPushButton("↺")
        self._cursor_reset_btn.setFixedSize(40, 28)
        self._cursor_reset_btn.setToolTip("Reset cursor positions")
        self._cursor_reset_btn.setStyleSheet(
            "QPushButton { font-size: 20px; color: #cccccc; "
            "border: 1px solid #555555; border-radius: 4px; "
            "background-color: #3a3a3a; padding-bottom: 2px; }"
            "QPushButton:hover { background-color: #4a4a4a; "
            "border-color: #888888; color: #ffffff; }"
        )
        self._cursor_reset_btn.clicked.connect(
            lambda: self.cursor_reset_requested.emit()
        )
        cursor_row.addWidget(self._cursor_reset_btn)

        layout.addLayout(cursor_row)

    def _on_autoscale(self):
        self.autoscale_requested.emit()

    def _on_meas_toggled(self):
        self._meas_visible = self._meas_btn.isChecked()
        text = "ON" if self._meas_visible else "OFF"
        self._meas_btn.setText(f"Measurements: {text}")
        self.measurement_bar_toggled.emit(self._meas_visible)

    def _on_dmm_toggled(self):
        active = self._dmm_btn.isChecked()
        text = "ON" if active else "OFF"
        self._dmm_btn.setText(f"DMM Mode: {text}")
        # Disable scope-only buttons in DMM mode
        self._autoscale_btn.setEnabled(not active)
        self._meas_btn.setEnabled(not active)
        self._cursor_btn.setEnabled(not active)
        self._cursor_reset_btn.setEnabled(not active)
        self.dmm_mode_toggled.emit(active)

    def _on_cursor_clicked(self):
        self._cursor_idx = (self._cursor_idx + 1) % len(self._CURSOR_MODES)
        mode, label = self._CURSOR_MODES[self._cursor_idx]
        self._cursor_btn.setText(label)
        self.cursor_mode_changed.emit(mode)

    # --- Public API ---

    def set_autoscale_enabled(self, enabled: bool):
        """Enable/disable the autoscale button (e.g., when not connected)."""
        self._autoscale_btn.setEnabled(enabled)

    def set_dmm_mode(self, active: bool):
        """Programmatically toggle DMM mode."""
        self._dmm_btn.setChecked(active)
        self._on_dmm_toggled()

    def set_cursor_mode(self, mode: str):
        """Programmatically set the cursor mode and update the button label.

        Does NOT emit cursor_mode_changed (caller is responsible for
        updating the waveform widget and readout directly).
        """
        for i, (m, label) in enumerate(self._CURSOR_MODES):
            if m == mode:
                self._cursor_idx = i
                self._cursor_btn.setText(label)
                return
