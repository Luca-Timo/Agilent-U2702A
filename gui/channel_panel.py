"""
Vertical (channel) control panel — Keysight-inspired layout.

For ≤4 channels: per-channel columns side by side, each with its own
V/div knob, Offset knob, coupling dropdown, and big colored channel button.

For >4 channels: falls back to selection buttons + single control strip.
"""

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QComboBox, QCheckBox, QPushButton, QSizePolicy, QFrame, QInputDialog,
)

from gui.theme import (
    VDIV_VALUES, format_vdiv, format_voltage, channel_color, NUM_CHANNELS,
)
from gui.knob_widget import RotaryKnob


@dataclass
class ChannelState:
    """Per-channel state."""
    enabled: bool = False
    v_per_div: float = 1.0
    v_per_div_index: int = 7   # Index in VDIV_VALUES (1.0 V/div)
    offset: float = 0.0
    coupling: str = "DC"
    bw_limit: bool = False
    probe_factor: float = 1.0


class ChannelColumn(QWidget):
    """Single channel control column — colored button + knobs + coupling."""

    channel_toggled = Signal(int, bool)    # channel, enabled
    vdiv_changed = Signal(int, float)
    offset_changed = Signal(int, float)
    coupling_changed = Signal(int, str)
    bwlimit_changed = Signal(int, bool)
    probe_changed = Signal(int, float)

    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self._channel = channel
        self._color = channel_color(channel)
        self._enabled = (channel == 1)  # CH1 enabled by default
        self._prev_probe_idx = 0
        self._current_vdiv = VDIV_VALUES[7]  # 1.0 V/div default
        self._probe_factor = 1.0

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # Big colored channel button (like Keysight 1/2/3/4 buttons)
        self._ch_btn = QPushButton(str(self._channel))
        self._ch_btn.setFixedSize(50, 40)
        self._ch_btn.setCheckable(True)
        self._ch_btn.setChecked(self._enabled)
        font = self._ch_btn.font()
        font.setPointSize(16)
        font.setBold(True)
        self._ch_btn.setFont(font)
        self._ch_btn.clicked.connect(self._on_toggle)
        self._update_button_style()
        layout.addWidget(self._ch_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # V/div knob
        self._vdiv_knob = RotaryKnob("V/div")
        self._vdiv_knob.set_values(VDIV_VALUES, 7)
        self._vdiv_knob.set_format_func(format_vdiv)
        self._vdiv_knob.value_changed.connect(self._on_vdiv_changed)
        layout.addWidget(self._vdiv_knob, alignment=Qt.AlignmentFlag.AlignCenter)

        # Effective V/div label (shown when probe ≠ 1x)
        self._effective_label = QLabel("")
        self._effective_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._effective_label.setStyleSheet(
            f"color: {self._color}; font-size: 9px; "
            "font-family: Menlo, monospace;"
        )
        self._effective_label.setVisible(False)
        layout.addWidget(self._effective_label,
                         alignment=Qt.AlignmentFlag.AlignCenter)

        # Offset knob
        self._offset_knob = RotaryKnob("Offset")
        self._offset_knob.set_range(-50.0, 50.0, 0.1, 0.0)
        self._offset_knob.set_format_func(format_voltage)
        self._offset_knob.value_changed.connect(
            lambda v: self.offset_changed.emit(self._channel, v)
        )
        layout.addWidget(self._offset_knob, alignment=Qt.AlignmentFlag.AlignCenter)

        # Coupling dropdown
        cpl_layout = QHBoxLayout()
        self._coupling_combo = QComboBox()
        self._coupling_combo.addItems(["DC", "AC"])
        self._coupling_combo.setFixedWidth(55)
        self._coupling_combo.currentTextChanged.connect(
            lambda v: self.coupling_changed.emit(self._channel, v)
        )
        cpl_layout.addStretch()
        cpl_layout.addWidget(self._coupling_combo)
        cpl_layout.addStretch()
        layout.addLayout(cpl_layout)

        # Probe dropdown
        prb_layout = QHBoxLayout()
        self._probe_combo = QComboBox()
        self._probe_combo.addItems(["1x", "10x", "100x", "1000x", "Custom..."])
        self._probe_combo.setFixedWidth(75)
        self._probe_combo.currentTextChanged.connect(self._on_probe_changed)
        prb_layout.addStretch()
        prb_layout.addWidget(self._probe_combo)
        prb_layout.addStretch()
        layout.addLayout(prb_layout)

        layout.addStretch()

    def _update_button_style(self):
        if self._enabled:
            self._ch_btn.setStyleSheet(
                f"QPushButton {{ background-color: {self._color}; "
                f"color: black; font-weight: bold; "
                f"border: 2px solid {self._color}; border-radius: 6px; }}"
                f"QPushButton:hover {{ background-color: {self._color}; "
                f"border: 3px solid white; }}"
            )
        else:
            self._ch_btn.setStyleSheet(
                f"QPushButton {{ background-color: #2a2a2a; "
                f"color: {self._color}; font-weight: bold; "
                f"border: 2px solid #444444; border-radius: 6px; }}"
                f"QPushButton:hover {{ border-color: {self._color}; }}"
            )

    def _on_toggle(self):
        self._enabled = self._ch_btn.isChecked()
        self._update_button_style()
        self.channel_toggled.emit(self._channel, self._enabled)

    def _on_vdiv_changed(self, v: float):
        self._current_vdiv = v
        self._update_effective_label()
        self.vdiv_changed.emit(self._channel, v)

    def _on_probe_changed(self, text: str):
        if text == "Custom...":
            value, ok = QInputDialog.getDouble(
                self, "Custom Probe Factor",
                f"Probe attenuation for CH{self._channel}:",
                value=self._probe_factor, min=0.001,
                max=10000.0, decimals=3,
            )
            if ok and value > 0:
                self._probe_combo.blockSignals(True)
                idx = self._probe_combo.count() - 1
                self._probe_combo.setItemText(idx, f"{value:g}x")
                self._probe_combo.setCurrentIndex(idx)
                self._probe_combo.blockSignals(False)
                self._prev_probe_idx = idx
                self._probe_factor = value
                self._update_effective_label()
                self.probe_changed.emit(self._channel, value)
            else:
                self._probe_combo.blockSignals(True)
                self._probe_combo.setCurrentIndex(self._prev_probe_idx)
                self._probe_combo.blockSignals(False)
            return
        self._prev_probe_idx = self._probe_combo.currentIndex()
        factor = float(text.replace("x", ""))
        self._probe_factor = factor
        self._update_effective_label()
        self.probe_changed.emit(self._channel, factor)

    def _update_effective_label(self):
        """Show effective V/div when probe factor != 1x."""
        if self._probe_factor != 1.0:
            eff = self._current_vdiv * self._probe_factor
            self._effective_label.setText(f"Eff: {format_vdiv(eff)}")
            self._effective_label.setVisible(True)
        else:
            self._effective_label.setVisible(False)

    # --- Public API ---

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._ch_btn.setChecked(enabled)
        self._update_button_style()

    def set_vdiv(self, value: float):
        self._current_vdiv = value
        self._vdiv_knob.blockSignals(True)
        self._vdiv_knob.set_value(value)
        self._vdiv_knob.blockSignals(False)
        self._update_effective_label()

    def set_offset(self, value: float):
        self._offset_knob.blockSignals(True)
        self._offset_knob.set_value(value)
        self._offset_knob.blockSignals(False)

    def set_coupling(self, coupling: str):
        self._coupling_combo.blockSignals(True)
        idx = self._coupling_combo.findText(coupling)
        if idx >= 0:
            self._coupling_combo.setCurrentIndex(idx)
        self._coupling_combo.blockSignals(False)

    def set_probe(self, factor: float):
        self._probe_combo.blockSignals(True)
        text = f"{factor:g}x"
        idx = self._probe_combo.findText(text)
        if idx >= 0:
            self._probe_combo.setCurrentIndex(idx)
        else:
            # Custom value — update last item
            last = self._probe_combo.count() - 1
            self._probe_combo.setItemText(last, text)
            self._probe_combo.setCurrentIndex(last)
        self._prev_probe_idx = self._probe_combo.currentIndex()
        self._probe_factor = factor
        self._probe_combo.blockSignals(False)
        self._update_effective_label()


class ChannelPanel(QGroupBox):
    """Vertical controls — Keysight-style per-channel columns.

    Signals:
        channel_selected(int) — active channel changed (for display purposes)
        channel_enabled(int, bool) — channel enable/disable toggled
        vdiv_changed(int, float) — V/div changed for channel
        offset_changed(int, float) — offset changed for channel
        coupling_changed(int, str) — coupling changed for channel
        bwlimit_changed(int, bool) — BW limit changed for channel
        probe_changed(int, float) — probe factor changed for channel
    """

    channel_selected = Signal(int)
    channel_enabled = Signal(int, bool)
    vdiv_changed = Signal(int, float)
    offset_changed = Signal(int, float)
    coupling_changed = Signal(int, str)
    bwlimit_changed = Signal(int, bool)
    probe_changed = Signal(int, float)

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__("VERTICAL", parent)
        self._num_channels = num_channels
        self._active_channel = 1
        self._columns: dict[int, ChannelColumn] = {}
        self._states: dict[int, ChannelState] = {}

        # Initialize per-channel state
        for ch in range(1, num_channels + 1):
            state = ChannelState()
            if ch == 1:
                state.enabled = True
            self._states[ch] = state

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(4)

        for ch in range(1, self._num_channels + 1):
            col = ChannelColumn(ch)

            # Connect signals
            col.channel_toggled.connect(self._on_channel_toggled)
            col.vdiv_changed.connect(self._on_vdiv_changed)
            col.offset_changed.connect(self._on_offset_changed)
            col.coupling_changed.connect(self._on_coupling_changed)
            col.probe_changed.connect(self._on_probe_changed)

            self._columns[ch] = col
            layout.addWidget(col)

            # Add separator between channels
            if ch < self._num_channels:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet("color: #333333;")
                layout.addWidget(sep)

    def _on_channel_toggled(self, ch: int, enabled: bool):
        self._states[ch].enabled = enabled
        self.channel_enabled.emit(ch, enabled)

    def _on_vdiv_changed(self, ch: int, value: float):
        self._states[ch].v_per_div = value
        self.vdiv_changed.emit(ch, value)

    def _on_offset_changed(self, ch: int, value: float):
        self._states[ch].offset = value
        self.offset_changed.emit(ch, value)

    def _on_coupling_changed(self, ch: int, text: str):
        self._states[ch].coupling = text
        self.coupling_changed.emit(ch, text)

    def _on_probe_changed(self, ch: int, factor: float):
        self._states[ch].probe_factor = factor
        self.probe_changed.emit(ch, factor)

    # --- Public API ---

    def get_state(self, ch: int) -> ChannelState:
        return self._states[ch]

    def get_enabled_channels(self) -> list[int]:
        return [ch for ch, s in self._states.items() if s.enabled]

    def set_channel_state(self, ch: int, enabled: bool = None,
                          v_per_div: float = None, offset: float = None,
                          coupling: str = None, bw_limit: bool = None):
        """Set channel state programmatically (e.g., from init sequence)."""
        state = self._states[ch]
        col = self._columns.get(ch)

        if enabled is not None:
            state.enabled = enabled
            if col:
                col.set_enabled(enabled)
        if v_per_div is not None:
            state.v_per_div = v_per_div
            if col:
                col.set_vdiv(v_per_div)
        if offset is not None:
            state.offset = offset
            if col:
                col.set_offset(offset)
        if coupling is not None:
            state.coupling = coupling
            if col:
                col.set_coupling(coupling)
        if bw_limit is not None:
            state.bw_limit = bw_limit
