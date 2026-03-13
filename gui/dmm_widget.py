"""
DMM (multimeter) display widget — large digital voltage readout.

Replaces the waveform display when DMM mode is active.
Shows per-channel voltage (DC / AC RMS / AC+DC RMS), frequency,
and running Min/Max/Average tracking.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy, QButtonGroup,
)
from PySide6.QtGui import QFont

from gui.theme import (
    NUM_CHANNELS, channel_color, format_voltage, format_frequency,
    BG_PLOT, BG_DARK, TEXT_SECONDARY, ACCENT_BLUE,
)
from processing.dmm import DMMAccumulator, DMMReading, DMMMode


# ---------------------------------------------------------------------------
#  Per-channel card
# ---------------------------------------------------------------------------

class ChannelDMMCard(QFrame):
    """Single-channel DMM readout card.

    Shows:
    - Channel label (colored, top-left)
    - Primary voltage reading (large font, channel-colored)
    - Min / Max / Avg row (smaller font)
    - Frequency reading (smaller font)
    """

    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self._channel = channel
        self._color = channel_color(channel)

        self.setStyleSheet(
            f"ChannelDMMCard {{ background-color: {BG_PLOT}; "
            f"border: 2px solid #333333; border-radius: 8px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._setup_ui()

    # --- UI ---

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        # Channel label
        self._ch_label = QLabel(f"CH{self._channel}")
        self._ch_label.setStyleSheet(
            f"color: {self._color}; font-size: 14px; font-weight: bold; "
            "border: none;"
        )
        layout.addWidget(self._ch_label)

        layout.addStretch(1)

        # Primary voltage readout — large, centered, channel-colored
        self._primary_label = QLabel("--- V")
        self._primary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._primary_label.setFont(QFont("Menlo", 48, QFont.Weight.Bold))
        self._primary_label.setStyleSheet(
            f"color: {self._color}; border: none;"
        )
        layout.addWidget(self._primary_label)

        layout.addStretch(1)

        # Min / Max / Avg row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)
        stat_css = (
            f"color: {TEXT_SECONDARY}; font-size: 12px; "
            "font-family: Menlo, monospace; border: none;"
        )

        self._min_label = QLabel("Min: ---")
        self._min_label.setStyleSheet(stat_css)
        stats_row.addWidget(self._min_label)

        self._max_label = QLabel("Max: ---")
        self._max_label.setStyleSheet(stat_css)
        stats_row.addWidget(self._max_label)

        self._avg_label = QLabel("Avg: ---")
        self._avg_label.setStyleSheet(stat_css)
        stats_row.addWidget(self._avg_label)

        stats_row.addStretch()

        self._count_label = QLabel("n=0")
        self._count_label.setStyleSheet(
            "color: #444444; font-size: 10px; "
            "font-family: Menlo, monospace; border: none;"
        )
        stats_row.addWidget(self._count_label)

        layout.addLayout(stats_row)

        # Frequency
        self._freq_label = QLabel("Freq: ---")
        self._freq_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; "
            "font-family: Menlo, monospace; border: none;"
        )
        layout.addWidget(self._freq_label)

    # --- Public ---

    def update_reading(self, reading: DMMReading):
        """Update all display fields from a DMMReading."""
        self._primary_label.setText(format_voltage(reading.primary))

        self._min_label.setText(f"Min: {format_voltage(reading.v_min)}")
        self._max_label.setText(f"Max: {format_voltage(reading.v_max)}")
        self._avg_label.setText(f"Avg: {format_voltage(reading.v_avg)}")
        self._count_label.setText(f"n={reading.sample_count}")

        if reading.frequency is not None:
            self._freq_label.setText(
                f"Freq: {format_frequency(reading.frequency)}"
            )
        else:
            self._freq_label.setText("Freq: ---")

    def clear(self):
        """Clear all readings to placeholder dashes."""
        self._primary_label.setText("--- V")
        self._min_label.setText("Min: ---")
        self._max_label.setText("Max: ---")
        self._avg_label.setText("Avg: ---")
        self._count_label.setText("n=0")
        self._freq_label.setText("Freq: ---")

    def set_color(self, color: str):
        """Update channel color (e.g. from settings dialog)."""
        self._color = color
        self._ch_label.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold; "
            "border: none;"
        )
        self._primary_label.setStyleSheet(f"color: {color}; border: none;")


# ---------------------------------------------------------------------------
#  Full DMM view
# ---------------------------------------------------------------------------

_MODE_BTN_STYLE = (
    "QPushButton {{ font-size: 11px; font-weight: bold; "
    "border: 1px solid #555555; border-radius: 4px; "
    "padding: 4px 12px; color: #cccccc; background-color: #2a2a2a; }}"
    "QPushButton:checked {{ background-color: {accent}; color: white; "
    "border-color: {accent}; }}"
    "QPushButton:hover {{ border-color: #888888; }}"
)


class DMMWidget(QWidget):
    """Full DMM display — mode buttons + per-channel cards.

    Signals:
        mode_changed(str) — user changed measurement mode
        reset_requested() — user clicked Reset Min/Max
    """

    mode_changed = Signal(str)
    reset_requested = Signal()

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__(parent)
        self._num_channels = num_channels
        self._mode = DMMMode.DC
        self._cards: dict[int, ChannelDMMCard] = {}
        self._accumulators: dict[int, DMMAccumulator] = {}
        self._channel_visible: dict[int, bool] = {}

        for ch in range(1, num_channels + 1):
            self._accumulators[ch] = DMMAccumulator()
            self._channel_visible[ch] = (ch == 1)

        self.setStyleSheet(f"background-color: {BG_DARK};")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # --- Top bar: mode buttons + reset ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)

        btn_style = _MODE_BTN_STYLE.format(accent=ACCENT_BLUE)
        for label, mode_val in [("DC", DMMMode.DC),
                                ("AC RMS", DMMMode.AC_RMS),
                                ("AC+DC RMS", DMMMode.AC_DC_RMS)]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(mode_val == DMMMode.DC)
            btn.setFixedHeight(32)
            btn.setMinimumWidth(80)
            btn.setStyleSheet(btn_style)
            btn.setProperty("dmm_mode", mode_val)
            self._mode_group.addButton(btn)
            top_bar.addWidget(btn)

        self._mode_group.buttonClicked.connect(self._on_mode_clicked)

        top_bar.addStretch()

        self._reset_btn = QPushButton("Reset Min/Max")
        self._reset_btn.setFixedHeight(32)
        self._reset_btn.setMinimumWidth(120)
        self._reset_btn.setStyleSheet(
            f"QPushButton {{ background-color: {ACCENT_BLUE}; color: white; "
            f"font-weight: bold; font-size: 11px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: #5aafff; }}"
        )
        self._reset_btn.clicked.connect(self._on_reset)
        top_bar.addWidget(self._reset_btn)

        layout.addLayout(top_bar)

        # --- Per-channel cards ---
        for ch in range(1, self._num_channels + 1):
            card = ChannelDMMCard(ch)
            card.setVisible(self._channel_visible.get(ch, False))
            self._cards[ch] = card
            layout.addWidget(card, stretch=1)

    # --- Internal ---

    def _on_mode_clicked(self, btn):
        mode = btn.property("dmm_mode")
        if mode and mode != self._mode:
            self._mode = mode
            # Reset accumulators — values are incomparable across modes
            for acc in self._accumulators.values():
                acc.reset()
            for card in self._cards.values():
                card.clear()
            self.mode_changed.emit(mode)

    def _on_reset(self):
        for acc in self._accumulators.values():
            acc.reset()
        for card in self._cards.values():
            card.clear()
        self.reset_requested.emit()

    # --- Public API ---

    def update_waveform(self, channel: int, voltage, time_axis,
                        probe_factor: float):
        """Process a new waveform frame and update the display.

        Called from main_window._on_waveform_ready when in DMM mode.

        Args:
            channel: Channel number (1-indexed).
            voltage: Scope-space voltage array.
            time_axis: Time axis array.
            probe_factor: Probe attenuation multiplier.
        """
        acc = self._accumulators.get(channel)
        card = self._cards.get(channel)
        if acc is None or card is None:
            return

        reading = acc.update(voltage, time_axis, probe_factor, self._mode)
        card.update_reading(reading)

    def set_channel_visible(self, channel: int, visible: bool):
        """Show/hide a channel card (synced with channel enable/disable)."""
        self._channel_visible[channel] = visible
        if channel in self._cards:
            self._cards[channel].setVisible(visible)

    def set_channel_color(self, channel: int, color: str):
        """Update channel color from settings."""
        if channel in self._cards:
            self._cards[channel].set_color(color)

    def reset_all(self):
        """Reset all accumulators and clear display."""
        self._on_reset()

    @property
    def mode(self) -> str:
        return self._mode
