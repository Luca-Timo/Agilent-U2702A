"""
Utility panel — Autoscale, measurement bar toggle, cursor controls.

Sits at the top of the right sidebar, above HORIZONTAL / TRIGGER / VERTICAL.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton

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

        # --- Cursor carousel button ---
        mode, label = self._CURSOR_MODES[0]
        self._cursor_btn = QPushButton(label)
        self._cursor_btn.setFixedHeight(28)
        self._cursor_btn.setStyleSheet(
            "QPushButton { font-size: 11px; }"
        )
        self._cursor_btn.clicked.connect(self._on_cursor_clicked)
        layout.addWidget(self._cursor_btn)

    def _on_autoscale(self):
        self.autoscale_requested.emit()

    def _on_meas_toggled(self):
        self._meas_visible = self._meas_btn.isChecked()
        text = "ON" if self._meas_visible else "OFF"
        self._meas_btn.setText(f"Measurements: {text}")
        self.measurement_bar_toggled.emit(self._meas_visible)

    def _on_cursor_clicked(self):
        self._cursor_idx = (self._cursor_idx + 1) % len(self._CURSOR_MODES)
        mode, label = self._CURSOR_MODES[self._cursor_idx]
        self._cursor_btn.setText(label)
        self.cursor_mode_changed.emit(mode)

    # --- Public API ---

    def set_autoscale_enabled(self, enabled: bool):
        """Enable/disable the autoscale button (e.g., when not connected)."""
        self._autoscale_btn.setEnabled(enabled)
