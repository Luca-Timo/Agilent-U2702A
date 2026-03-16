"""
Cursor readout widget — displays ΔT, 1/ΔT, ΔV for active cursors.

Compact bar below the waveform, shown only when cursors are active.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)

from gui.theme import (
    NUM_CHANNELS, channel_color,
    format_voltage, format_current, format_frequency, format_time,
)


class CursorReadout(QFrame):
    """Cursor measurement readout — shows cursor positions and deltas.

    Layout (single row, compact):
        Time mode:    C-X1: -500 µs   C-X2: +500 µs   ΔT: 1.00 ms   1/ΔT: 1.00 kHz
        Voltage mode: [CH1] C-Y1: 1.20 V  C-Y2: -800 mV  ΔV: 2.00 V
        Both mode:    Both rows combined into one line

    The channel selector determines which channel the Y cursors
    are measuring, so the readout converts display-space positions
    to that channel's physical units (V or A).
    """

    channel_selected = Signal(int)  # Emitted when user cycles channel button

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "off"
        self._current_mode = False  # True = display amps instead of volts
        self._selected_ch = 1       # Which channel the Y cursors measure

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
        self._tc1_label = QLabel("C-X1:")
        self._tc1_label.setStyleSheet(label_style)
        self._tc1_value = QLabel("---")
        self._tc1_value.setStyleSheet(value_style)
        self._tc1_value.setMinimumWidth(80)

        self._tc2_label = QLabel("C-X2:")
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

        # Channel selector button — determines which channel Y cursors measure
        self._ch_btn = QPushButton("CH1")
        self._ch_btn.setFixedSize(38, 20)
        self._ch_btn.setToolTip("Select channel for Y cursor measurement")
        self._update_ch_btn_style()
        self._ch_btn.clicked.connect(self._on_ch_clicked)

        # Voltage/current cursor labels
        self._vc1_label = QLabel("C-Y1:")
        self._vc1_label.setStyleSheet(label_style)
        self._vc1_value = QLabel("---")
        self._vc1_value.setStyleSheet(value_style)
        self._vc1_value.setMinimumWidth(80)

        self._vc2_label = QLabel("C-Y2:")
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
            self._ch_btn,
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

    def _update_ch_btn_style(self):
        """Update channel button colour to match the selected channel."""
        color = channel_color(self._selected_ch)
        self._ch_btn.setStyleSheet(
            f"QPushButton {{ font-size: 9px; font-weight: bold; "
            f"color: white; background-color: {color}; "
            f"border: 1px solid {color}; border-radius: 3px; "
            f"padding: 0px; }}"
            f"QPushButton:hover {{ border-color: #ffffff; }}"
        )

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
        """Update voltage/current cursor readout values.

        Values should already be converted to physical units for the
        selected channel (volts or amps) by the caller.
        """
        fmt = format_current if self._current_mode else format_voltage
        self._vc1_value.setText(fmt(v1))
        self._vc2_value.setText(fmt(v2))

        dv = abs(v2 - v1)
        self._dv_value.setText(fmt(dv))

    def _on_ch_clicked(self):
        """Cycle through channels: CH1 → CH2 → CH1 → …"""
        self._selected_ch = (self._selected_ch % NUM_CHANNELS) + 1
        self._ch_btn.setText(f"CH{self._selected_ch}")
        self._update_ch_btn_style()
        self.channel_selected.emit(self._selected_ch)

    def set_current_mode(self, active: bool):
        """Set the unit display mode (voltage or current).

        Called by main_window when the selected channel's current mode
        is known, so the readout shows the correct ΔV / ΔI label and
        uses the right formatter.
        """
        self._current_mode = active
        self._dv_label.setText("ΔI:" if active else "ΔV:")

    def set_channel(self, ch: int):
        """Programmatically select a channel (without emitting signal)."""
        self._selected_ch = ch
        self._ch_btn.setText(f"CH{ch}")
        self._update_ch_btn_style()

    @property
    def selected_channel(self) -> int:
        """Currently selected channel for Y cursor measurement."""
        return self._selected_ch
