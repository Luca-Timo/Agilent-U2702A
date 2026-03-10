"""
Horizontal (timebase) control panel — Keysight style.

T/div and position knobs side by side.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout

from gui.theme import TDIV_VALUES, format_tdiv, format_time
from gui.knob_widget import RotaryKnob


class TimebasePanel(QGroupBox):
    """Horizontal controls — T/div and position side by side.

    Signals:
        tdiv_changed(float) — T/div changed
        position_changed(float) — horizontal position changed
    """

    tdiv_changed = Signal(float)
    position_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("HORIZONTAL", parent)

        self._t_per_div = 1e-3
        self._position = 0.0

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(8)

        # T/div knob
        self._tdiv_knob = RotaryKnob("T/div")
        self._tdiv_knob.set_values(TDIV_VALUES, 18)  # Default 1ms
        self._tdiv_knob.set_format_func(format_tdiv)
        self._tdiv_knob.value_changed.connect(self._on_tdiv_changed)
        layout.addWidget(self._tdiv_knob, alignment=Qt.AlignmentFlag.AlignCenter)

        # Position knob
        self._pos_knob = RotaryKnob("Position")
        self._pos_knob.set_range(-1.0, 1.0, 0.001, 0.0)
        self._pos_knob.set_format_func(format_time)
        self._pos_knob.value_changed.connect(self._on_position_changed)
        layout.addWidget(self._pos_knob, alignment=Qt.AlignmentFlag.AlignCenter)

    def _on_tdiv_changed(self, value: float):
        self._t_per_div = value
        # Update position knob range based on T/div
        max_pos = 5 * value  # ±5 divisions
        self._pos_knob.set_range(-max_pos, max_pos, value / 10, self._position)
        self.tdiv_changed.emit(value)

    def _on_position_changed(self, value: float):
        self._position = value
        self.position_changed.emit(value)

    # --- Public API ---

    @property
    def t_per_div(self) -> float:
        return self._t_per_div

    @property
    def position(self) -> float:
        return self._position

    def set_tdiv(self, value: float):
        """Set T/div programmatically."""
        self._tdiv_knob.set_value(value)
        self._t_per_div = value

    def set_position(self, value: float):
        """Set position programmatically."""
        self._pos_knob.set_value(value)
        self._position = value
