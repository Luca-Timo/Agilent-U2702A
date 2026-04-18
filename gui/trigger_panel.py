"""
Trigger control panel.

Edge-trigger primary controls (level / source / slope / sweep / coupling)
plus an optional pulse-width (glitch) sub-group that appears when the
trigger mode is switched to Pulse Width.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
)

from gui.theme import format_time, format_voltage, NUM_CHANNELS
from gui.knob_widget import RotaryKnob


class TriggerPanel(QGroupBox):
    """Trigger controls — mode selector, edge controls, optional pulse-width.

    Signals:
        level_changed(float) — trigger level changed
        source_changed(str) — trigger source changed (e.g., "CHAN1")
        slope_changed(str) — trigger slope changed (e.g., "POS")
        sweep_changed(str) — sweep mode changed (e.g., "AUTO")
        coupling_changed(str) — trigger coupling changed (e.g., "DC")
        mode_changed(str) — trigger mode changed: "EDGE" or "GLITCH"
        pulse_polarity_changed(str) — "POS" or "NEG"
        pulse_qualifier_changed(str) — "LESS" / "GRE" / "RANG" / "OUTRANG"
        pulse_threshold_changed(float) — seconds; meaning depends on qualifier
    """

    level_changed = Signal(float)
    source_changed = Signal(str)
    slope_changed = Signal(str)
    sweep_changed = Signal(str)
    coupling_changed = Signal(str)
    mode_changed = Signal(str)
    pulse_polarity_changed = Signal(str)
    pulse_qualifier_changed = Signal(str)
    pulse_threshold_changed = Signal(float)

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__("TRIGGER", parent)
        self._num_channels = num_channels
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Trigger mode (Edge / Pulse Width)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Edge",        "EDGE")
        self._mode_combo.addItem("Pulse Width", "GLITCH")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_index_changed)
        mode_row.addWidget(self._mode_combo, stretch=1)
        layout.addLayout(mode_row)

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

        # --- Pulse-width subgroup (visible only when Mode=Pulse Width) ---
        self._pulse_group = QGroupBox("Pulse Width")
        pulse_v = QVBoxLayout(self._pulse_group)
        pulse_v.setSpacing(4)

        pol_row = QHBoxLayout()
        pol_row.addWidget(QLabel("Polarity:"))
        self._pulse_polarity_combo = QComboBox()
        self._pulse_polarity_combo.addItem("⎍ Positive", "POS")
        self._pulse_polarity_combo.addItem("⎎ Negative", "NEG")
        self._pulse_polarity_combo.currentIndexChanged.connect(
            self._on_pulse_polarity_changed,
        )
        pol_row.addWidget(self._pulse_polarity_combo, stretch=1)
        pulse_v.addLayout(pol_row)

        qual_row = QHBoxLayout()
        qual_row.addWidget(QLabel("Compare:"))
        self._pulse_qualifier_combo = QComboBox()
        # SCPI tokens as userData; human labels as text.
        self._pulse_qualifier_combo.addItem("> (greater than)", "GRE")
        self._pulse_qualifier_combo.addItem("< (less than)",    "LESS")
        self._pulse_qualifier_combo.addItem("within range",     "RANG")
        self._pulse_qualifier_combo.addItem("outside range",    "OUTRANG")
        self._pulse_qualifier_combo.currentIndexChanged.connect(
            self._on_pulse_qualifier_changed,
        )
        qual_row.addWidget(self._pulse_qualifier_combo, stretch=1)
        pulse_v.addLayout(qual_row)

        # Threshold knob — always in seconds. For the range/outrange
        # qualifiers this acts as the upper bound; the lower bound is
        # the "range-span" fraction (30% by default, hardcoded — if
        # the user needs fine-grained range setup, apply_setting
        # ("trigger.pulse.greater"/"less") from a script is the
        # richer path).
        self._pulse_threshold_knob = RotaryKnob("Threshold")
        # 33120A-ish range: 10 ns to 10 s, logarithmic-ish step.
        self._pulse_threshold_knob.set_range(10e-9, 10.0, 1e-6, 1e-3)
        self._pulse_threshold_knob.set_format_func(format_time)
        self._pulse_threshold_knob.value_changed.connect(
            self._on_pulse_threshold_changed,
        )
        pulse_v.addWidget(
            self._pulse_threshold_knob,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        layout.addWidget(self._pulse_group)
        self._pulse_group.setVisible(False)   # edge mode is the default

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

    def _on_mode_index_changed(self, index: int):
        mode = self._mode_combo.itemData(index) or "EDGE"
        self._pulse_group.setVisible(mode == "GLITCH")
        self.mode_changed.emit(mode)

    def _on_pulse_polarity_changed(self, index: int):
        val = self._pulse_polarity_combo.itemData(index)
        if val:
            self.pulse_polarity_changed.emit(val)

    def _on_pulse_qualifier_changed(self, index: int):
        val = self._pulse_qualifier_combo.itemData(index)
        if val:
            self.pulse_qualifier_changed.emit(val)

    def _on_pulse_threshold_changed(self, value: float):
        self.pulse_threshold_changed.emit(value)

    # --- Public API ---

    @property
    def level(self) -> float:
        return self._level_knob.value

    @property
    def source(self) -> str:
        return self._source_combo.currentText()

    @property
    def slope(self) -> str:
        return self._slope_combo.currentData()

    @property
    def sweep(self) -> str:
        return self._sweep_combo.currentText()

    @property
    def coupling(self) -> str:
        return self._coupling_combo.currentText()

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

    # -- Pulse-width accessors / setters -----------------------------

    @property
    def mode(self) -> str:
        return self._mode_combo.currentData() or "EDGE"

    def set_mode(self, mode: str):
        idx = self._mode_combo.findData(mode)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)
            self._pulse_group.setVisible(mode == "GLITCH")

    @property
    def pulse_polarity(self) -> str:
        return self._pulse_polarity_combo.currentData() or "POS"

    def set_pulse_polarity(self, polarity: str):
        idx = self._pulse_polarity_combo.findData(polarity)
        if idx >= 0:
            self._pulse_polarity_combo.setCurrentIndex(idx)

    @property
    def pulse_qualifier(self) -> str:
        return self._pulse_qualifier_combo.currentData() or "GRE"

    def set_pulse_qualifier(self, qualifier: str):
        idx = self._pulse_qualifier_combo.findData(qualifier)
        if idx >= 0:
            self._pulse_qualifier_combo.setCurrentIndex(idx)

    @property
    def pulse_threshold(self) -> float:
        return self._pulse_threshold_knob.value

    def set_pulse_threshold(self, seconds: float):
        self._pulse_threshold_knob.set_value(seconds)
