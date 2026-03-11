"""
Cursor readout widget — displays ΔT, 1/ΔT, ΔV for active cursors.

Compact bar below the waveform, shown only when cursors are active.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy,
)

from gui.theme import format_voltage, format_frequency, format_time


class CursorReadout(QFrame):
    """Cursor measurement readout — shows cursor positions and deltas.

    Layout (single row, compact):
        Time mode:    C1: -500 µs   C2: +500 µs   ΔT: 1.00 ms   1/ΔT: 1.00 kHz
        Voltage mode: C1: 1.20 V    C2: -800 mV    ΔV: 2.00 V
        Both mode:    Both rows combined into one line
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "off"

        self.setStyleSheet(
            "QFrame { border: 1px solid #333333; border-radius: 3px; "
            "background-color: #1a1a1a; }"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(16)

        label_style = (
            "color: #FF8800; font-size: 10px; font-weight: bold; "
            "font-family: Menlo, monospace; border: none;"
        )
        value_style = (
            "color: #cccccc; font-size: 10px; "
            "font-family: Menlo, monospace; border: none;"
        )

        # Time cursor labels
        self._tc1_label = QLabel("C1:")
        self._tc1_label.setStyleSheet(label_style)
        self._tc1_value = QLabel("---")
        self._tc1_value.setStyleSheet(value_style)
        self._tc1_value.setMinimumWidth(80)

        self._tc2_label = QLabel("C2:")
        self._tc2_label.setStyleSheet(label_style)
        self._tc2_value = QLabel("---")
        self._tc2_value.setStyleSheet(value_style)
        self._tc2_value.setMinimumWidth(80)

        self._dt_label = QLabel("ΔT:")
        self._dt_label.setStyleSheet(label_style)
        self._dt_value = QLabel("---")
        self._dt_value.setStyleSheet(value_style)
        self._dt_value.setMinimumWidth(80)

        self._inv_dt_label = QLabel("1/ΔT:")
        self._inv_dt_label.setStyleSheet(label_style)
        self._inv_dt_value = QLabel("---")
        self._inv_dt_value.setStyleSheet(value_style)
        self._inv_dt_value.setMinimumWidth(80)

        # Voltage cursor labels
        self._vc1_label = QLabel("C1:")
        self._vc1_label.setStyleSheet(label_style)
        self._vc1_value = QLabel("---")
        self._vc1_value.setStyleSheet(value_style)
        self._vc1_value.setMinimumWidth(80)

        self._vc2_label = QLabel("C2:")
        self._vc2_label.setStyleSheet(label_style)
        self._vc2_value = QLabel("---")
        self._vc2_value.setStyleSheet(value_style)
        self._vc2_value.setMinimumWidth(80)

        self._dv_label = QLabel("ΔV:")
        self._dv_label.setStyleSheet(label_style)
        self._dv_value = QLabel("---")
        self._dv_value.setStyleSheet(value_style)
        self._dv_value.setMinimumWidth(80)

        # Separator between time and voltage sections
        self._separator = QLabel("│")
        self._separator.setStyleSheet(
            "color: #444444; font-size: 10px; border: none;"
        )

        # Add all to layout
        self._time_widgets = [
            self._tc1_label, self._tc1_value,
            self._tc2_label, self._tc2_value,
            self._dt_label, self._dt_value,
            self._inv_dt_label, self._inv_dt_value,
        ]
        self._volt_widgets = [
            self._vc1_label, self._vc1_value,
            self._vc2_label, self._vc2_value,
            self._dv_label, self._dv_value,
        ]

        for w in self._time_widgets:
            layout.addWidget(w)
        layout.addWidget(self._separator)
        for w in self._volt_widgets:
            layout.addWidget(w)
        layout.addStretch()

        self._apply_visibility()

    def set_mode(self, mode: str):
        """Set cursor mode: "off", "time", "voltage", "both"."""
        self._mode = mode
        self._apply_visibility()

    def _apply_visibility(self):
        """Show/hide time and voltage sections based on mode."""
        show_time = self._mode in ("time", "both")
        show_volt = self._mode in ("voltage", "both")
        show_sep = show_time and show_volt

        for w in self._time_widgets:
            w.setVisible(show_time)
        for w in self._volt_widgets:
            w.setVisible(show_volt)
        self._separator.setVisible(show_sep)

    def update_time_cursors(self, t1: float, t2: float):
        """Update time cursor readout values."""
        self._tc1_value.setText(format_time(t1))
        self._tc2_value.setText(format_time(t2))

        dt = abs(t2 - t1)
        self._dt_value.setText(format_time(dt))

        if dt > 1e-15:
            self._inv_dt_value.setText(format_frequency(1.0 / dt))
        else:
            self._inv_dt_value.setText("---")

    def update_volt_cursors(self, v1: float, v2: float):
        """Update voltage cursor readout values."""
        self._vc1_value.setText(format_voltage(v1))
        self._vc2_value.setText(format_voltage(v2))

        dv = abs(v2 - v1)
        self._dv_value.setText(format_voltage(dv))
