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
    hold_toggled = Signal(bool)
    relative_toggled = Signal(bool)
    range_lock_toggled = Signal(bool)

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

        # --- DMM extras row: Hold / REL / Range Lock ---
        dmm_row = QHBoxLayout()
        dmm_row.setSpacing(4)

        self._hold_btn = QPushButton("Hold")
        self._hold_btn.setFixedHeight(28)
        self._hold_btn.setCheckable(True)
        self._hold_btn.setEnabled(False)
        self._hold_btn.setStyleSheet(self._dmm_extra_style(False))
        self._hold_btn.clicked.connect(self._on_hold_toggled)
        dmm_row.addWidget(self._hold_btn)

        self._rel_btn = QPushButton("REL")
        self._rel_btn.setFixedHeight(28)
        self._rel_btn.setCheckable(True)
        self._rel_btn.setEnabled(False)
        self._rel_btn.setStyleSheet(self._dmm_extra_style(False))
        self._rel_btn.clicked.connect(self._on_rel_toggled)
        dmm_row.addWidget(self._rel_btn)

        self._range_btn = QPushButton("Range: AUTO")
        self._range_btn.setFixedHeight(28)
        self._range_btn.setCheckable(True)
        self._range_btn.setEnabled(False)
        self._range_btn.setStyleSheet(self._dmm_extra_style(False))
        self._range_btn.clicked.connect(self._on_range_lock_toggled)
        dmm_row.addWidget(self._range_btn)

        layout.addLayout(dmm_row)

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

    @staticmethod
    def _dmm_extra_style(active_color: str | None = None) -> str:
        """Stylesheet for DMM extra buttons (Hold/REL/Range Lock).

        Args:
            active_color: Background colour when checked, or None for default.
        """
        base = (
            "QPushButton { font-size: 10px; font-weight: bold; "
            "border: 1px solid #555555; border-radius: 4px; "
            "padding: 2px 8px; color: #cccccc; background-color: #2a2a2a; }"
            "QPushButton:hover { border-color: #888888; }"
            "QPushButton:disabled { color: #555555; border-color: #3a3a3a; "
            "background-color: #222222; }"
        )
        if active_color:
            base += (
                f"QPushButton:checked {{ background-color: {active_color}; "
                f"color: white; border-color: {active_color}; }}"
            )
        else:
            base += (
                "QPushButton:checked { background-color: #555555; "
                "color: white; border-color: #777777; }"
            )
        return base

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
        # Enable/disable DMM extras
        self._hold_btn.setEnabled(active)
        self._rel_btn.setEnabled(active)
        self._range_btn.setEnabled(active)
        # Deactivate DMM extras when leaving DMM mode
        if not active:
            if self._hold_btn.isChecked():
                self._hold_btn.setChecked(False)
                self._on_hold_toggled()
            if self._rel_btn.isChecked():
                self._rel_btn.setChecked(False)
                self._on_rel_toggled()
            if self._range_btn.isChecked():
                self._range_btn.setChecked(False)
                self._on_range_lock_toggled()
        self.dmm_mode_toggled.emit(active)

    def _on_hold_toggled(self):
        active = self._hold_btn.isChecked()
        self._hold_btn.setText("HOLD" if active else "Hold")
        self._hold_btn.setStyleSheet(
            self._dmm_extra_style("#ccaa00" if active else None)
        )
        self.hold_toggled.emit(active)

    def _on_rel_toggled(self):
        active = self._rel_btn.isChecked()
        self._rel_btn.setText("Δ REL" if active else "REL")
        self._rel_btn.setStyleSheet(
            self._dmm_extra_style(ACCENT_BLUE if active else None)
        )
        self.relative_toggled.emit(active)

    def _on_range_lock_toggled(self):
        active = self._range_btn.isChecked()
        self._range_btn.setText("Range: LOCK" if active else "Range: AUTO")
        self._range_btn.setStyleSheet(
            self._dmm_extra_style("#cc5500" if active else None)
        )
        self.range_lock_toggled.emit(active)

    def _on_cursor_clicked(self):
        self._cursor_idx = (self._cursor_idx + 1) % len(self._CURSOR_MODES)
        mode, label = self._CURSOR_MODES[self._cursor_idx]
        self._cursor_btn.setText(label)
        self.cursor_mode_changed.emit(mode)

    # --- Public API ---

    @property
    def measurements_visible(self) -> bool:
        return self._meas_visible

    @property
    def cursor_mode(self) -> str:
        mode, _ = self._CURSOR_MODES[self._cursor_idx]
        return mode

    @property
    def dmm_mode(self) -> bool:
        return self._dmm_btn.isChecked()

    @property
    def hold_active(self) -> bool:
        return self._hold_btn.isChecked()

    @property
    def relative_active(self) -> bool:
        return self._rel_btn.isChecked()

    @property
    def range_locked(self) -> bool:
        return self._range_btn.isChecked()

    def set_measurements_visible(self, visible: bool):
        """Programmatically set measurement bar visibility."""
        self._meas_visible = visible
        self._meas_btn.setChecked(visible)
        text = "ON" if visible else "OFF"
        self._meas_btn.setText(f"Measurements: {text}")

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

    def set_hold(self, active: bool):
        """Programmatically set Hold state."""
        self._hold_btn.setChecked(active)
        self._on_hold_toggled()

    def set_relative(self, active: bool):
        """Programmatically set REL state."""
        self._rel_btn.setChecked(active)
        self._on_rel_toggled()

    def set_range_lock(self, active: bool):
        """Programmatically set Range Lock state."""
        self._range_btn.setChecked(active)
        self._on_range_lock_toggled()
