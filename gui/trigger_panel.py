"""
Trigger control panel.

Level knob, source/slope/sweep/coupling dropdowns.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
)

from gui.theme import format_voltage, NUM_CHANNELS
from gui.knob_widget import RotaryKnob


class TriggerPanel(QGroupBox):
    """Trigger controls — level knob + source/slope/sweep/coupling.

    Signals:
        level_changed(float) — trigger level changed
        source_changed(str) — trigger source changed (e.g., "CHAN1")
        slope_changed(str) — trigger slope changed (e.g., "POS")
        sweep_changed(str) — sweep mode changed (e.g., "AUTO")
        coupling_changed(str) — trigger coupling changed (e.g., "DC")
    """

    level_changed = Signal(float)
    source_changed = Signal(str)
    slope_changed = Signal(str)
    sweep_changed = Signal(str)
    coupling_changed = Signal(str)

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__("TRIGGER", parent)
        self._num_channels = num_channels
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Level knob
        self._level_knob = RotaryKnob("Level")
        self._level_knob.set_range(-50.0, 50.0, 0.1, 0.0)
        self._level_knob.set_format_func(format_voltage)
        self._level_knob.value_changed.connect(self._on_level_changed)
        layout.addWidget(self._level_knob, alignment=Qt.AlignmentFlag.AlignCenter)

        # Source dropdown
        src_layout = QHBoxLayout()
        src_layout.addWidget(QLabel("Source:"))
        self._source_combo = QComboBox()
        sources = [f"CHAN{ch}" for ch in range(1, self._num_channels + 1)]
        sources.append("EXT")
        self._source_combo.addItems(sources)
        self._source_combo.currentTextChanged.connect(self._on_source_changed)
        src_layout.addWidget(self._source_combo)
        layout.addLayout(src_layout)

        # Slope dropdown — display names with arrow icons, data values are SCPI
        slope_layout = QHBoxLayout()
        slope_layout.addWidget(QLabel("Slope:"))
        self._slope_combo = QComboBox()
        self._slope_combo.addItem("↗ POS", "POS")
        self._slope_combo.addItem("↘ NEG", "NEG")
        self._slope_combo.addItem("↕ EITH", "EITH")
        self._slope_combo.addItem("⇅ ALT", "ALT")
        self._slope_combo.currentIndexChanged.connect(self._on_slope_index_changed)
        slope_layout.addWidget(self._slope_combo)
        layout.addLayout(slope_layout)

        # Sweep mode dropdown
        sweep_layout = QHBoxLayout()
        sweep_layout.addWidget(QLabel("Sweep:"))
        self._sweep_combo = QComboBox()
        self._sweep_combo.addItems(["AUTO", "NORM"])
        self._sweep_combo.currentTextChanged.connect(self._on_sweep_changed)
        sweep_layout.addWidget(self._sweep_combo)
        layout.addLayout(sweep_layout)

        # Coupling dropdown
        cpl_layout = QHBoxLayout()
        cpl_layout.addWidget(QLabel("Coupling:"))
        self._coupling_combo = QComboBox()
        self._coupling_combo.addItems(["DC", "AC", "LFR", "HFR"])
        self._coupling_combo.currentTextChanged.connect(self._on_coupling_changed)
        cpl_layout.addWidget(self._coupling_combo)
        layout.addLayout(cpl_layout)

        layout.addStretch()

    def _on_level_changed(self, value: float):
        self.level_changed.emit(value)

    def _on_source_changed(self, text: str):
        self.source_changed.emit(text)

    def _on_slope_index_changed(self, index: int):
        slope = self._slope_combo.itemData(index)
        if slope:
            self.slope_changed.emit(slope)

    def _on_sweep_changed(self, text: str):
        self.sweep_changed.emit(text)

    def _on_coupling_changed(self, text: str):
        self.coupling_changed.emit(text)

    # --- Public API ---

    def set_level(self, value: float):
        self._level_knob.set_value(value)

    def set_source(self, source: str):
        idx = self._source_combo.findText(source)
        if idx >= 0:
            self._source_combo.setCurrentIndex(idx)

    def set_slope(self, slope: str):
        idx = self._slope_combo.findData(slope)
        if idx >= 0:
            self._slope_combo.setCurrentIndex(idx)

    def set_sweep(self, mode: str):
        idx = self._sweep_combo.findText(mode)
        if idx >= 0:
            self._sweep_combo.setCurrentIndex(idx)

    def set_coupling(self, coupling: str):
        idx = self._coupling_combo.findText(coupling)
        if idx >= 0:
            self._coupling_combo.setCurrentIndex(idx)
