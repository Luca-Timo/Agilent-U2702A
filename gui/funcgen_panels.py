"""
Control panels for function-generator windows.

Each panel emits a signal per setpoint it owns. The window wires those
signals to ``driver.apply_setting(key, value)``. Panels hold no
instrument state of their own — reflecting instrument state back into
the UI is done by the window calling ``set_*`` setters on the panel
from the acquisition result.

Panels (MVP):

  - ``FrequencyPanel``  — big frequency knob + SI preset buttons
  - ``AmplitudePanel``  — amplitude knob, offset knob, load termination
  - ``WaveformPanel``   — waveform shape picker + duty-cycle (for SQU)

When the plan expands past MVP (modulation, sweep, burst), each new
concern lands as its own panel file in the same style.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QComboBox, QSizePolicy,
)

from gui.knob_widget import RotaryKnob
from gui.theme import (
    format_frequency, format_voltage, format_percent,
)


# ---------------------------------------------------------------------
# Frequency panel
# ---------------------------------------------------------------------


class FrequencyPanel(QGroupBox):
    """Frequency knob plus SI-decade preset buttons.

    Emits ``frequency_changed(float)`` in Hz.
    """

    frequency_changed = Signal(float)

    # Quick-jump buttons — one per SI decade from 1 Hz to 10 MHz, which
    # covers the 33120A's 0.1 Hz – 15 MHz span at useful points.
    PRESETS_HZ = (1.0, 10.0, 100.0, 1_000.0, 10_000.0,
                  100_000.0, 1_000_000.0, 10_000_000.0)

    def __init__(self,
                 min_hz: float = 0.1, max_hz: float = 15_000_000.0,
                 initial_hz: float = 1000.0, parent=None):
        super().__init__("Frequency", parent)
        self._min = min_hz
        self._max = max_hz

        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        # Knob: log-ish feel by giving a small step; the RotaryKnob
        # handles drag-to-adjust and click-to-enter-exact-value.
        self._knob = RotaryKnob("Frequency")
        step = max(self._min, initial_hz / 100.0)
        self._knob.set_range(self._min, self._max, step, initial_hz)
        self._knob.set_format_func(format_frequency)
        self._knob.value_changed.connect(self._on_knob_changed)
        outer.addWidget(self._knob, alignment=Qt.AlignmentFlag.AlignCenter)

        # Preset row (two lines so they fit on a narrow panel).
        preset_grid = QGridLayout()
        preset_grid.setSpacing(4)
        for i, hz in enumerate(self.PRESETS_HZ):
            btn = QPushButton(format_frequency(hz))
            btn.setFixedHeight(24)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
            )
            btn.clicked.connect(
                lambda _=False, v=hz: self._on_preset_clicked(v),
            )
            preset_grid.addWidget(btn, i // 4, i % 4)
        outer.addLayout(preset_grid)

    # -- Public API ---------------------------------------------------

    def set_frequency(self, hz: float) -> None:
        """Programmatic update (from the instrument) — no signal."""
        # Clamp to range and set without emitting
        hz = max(self._min, min(self._max, hz))
        self._knob.blockSignals(True)
        try:
            self._knob.set_value(hz)
        finally:
            self._knob.blockSignals(False)

    @property
    def frequency(self) -> float:
        return self._knob.value

    # -- Internal -----------------------------------------------------

    def _on_knob_changed(self, value: float):
        self.frequency_changed.emit(value)

    def _on_preset_clicked(self, hz: float):
        self._knob.set_value(hz)
        self.frequency_changed.emit(hz)


# ---------------------------------------------------------------------
# Amplitude panel (amplitude + offset + output load)
# ---------------------------------------------------------------------


class AmplitudePanel(QGroupBox):
    """Amplitude and DC offset knobs, plus load-termination dropdown."""

    amplitude_changed = Signal(float)   # Vpp
    offset_changed = Signal(float)      # V
    load_changed = Signal(str)          # "50" or "INF"

    def __init__(self,
                 min_vpp: float = 0.05, max_vpp: float = 10.0,
                 initial_vpp: float = 1.0,
                 initial_offset: float = 0.0,
                 parent=None):
        super().__init__("Amplitude / Offset", parent)

        outer = QVBoxLayout(self)
        outer.setSpacing(6)

        knob_row = QHBoxLayout()
        knob_row.setSpacing(6)

        self._amp_knob = RotaryKnob("Amplitude")
        self._amp_knob.set_range(
            min_vpp, max_vpp, max_vpp / 1000.0, initial_vpp,
        )
        self._amp_knob.set_format_func(
            lambda v: format_voltage(v) + "pp",
        )
        self._amp_knob.value_changed.connect(self.amplitude_changed.emit)
        knob_row.addWidget(self._amp_knob)

        self._offset_knob = RotaryKnob("Offset")
        # 33120A offset range: ±5 V (into 50 Ω). Give a comfortable span.
        self._offset_knob.set_range(-5.0, 5.0, 0.01, initial_offset)
        self._offset_knob.set_format_func(format_voltage)
        self._offset_knob.value_changed.connect(self.offset_changed.emit)
        knob_row.addWidget(self._offset_knob)

        outer.addLayout(knob_row)

        # Load termination — 50 Ω (matched, most common) or HiZ.
        load_row = QHBoxLayout()
        load_row.addWidget(QLabel("Load:"))
        self._load_combo = QComboBox()
        self._load_combo.addItems(["50 Ω", "HiZ (INF)"])
        self._load_combo.currentTextChanged.connect(self._on_load_changed)
        load_row.addWidget(self._load_combo, stretch=1)
        outer.addLayout(load_row)

    # -- Public API ---------------------------------------------------

    def set_amplitude(self, vpp: float) -> None:
        self._amp_knob.blockSignals(True)
        try:
            self._amp_knob.set_value(vpp)
        finally:
            self._amp_knob.blockSignals(False)

    def set_offset(self, volts: float) -> None:
        self._offset_knob.blockSignals(True)
        try:
            self._offset_knob.set_value(volts)
        finally:
            self._offset_knob.blockSignals(False)

    def set_load(self, load: str) -> None:
        self._load_combo.blockSignals(True)
        try:
            self._load_combo.setCurrentIndex(0 if load == "50" else 1)
        finally:
            self._load_combo.blockSignals(False)

    # -- Internal -----------------------------------------------------

    def _on_load_changed(self, text: str):
        # Normalise to the driver's key namespace ("50" / "INF").
        self.load_changed.emit("50" if text.startswith("50") else "INF")


# ---------------------------------------------------------------------
# Waveform panel (shape picker + square-wave duty)
# ---------------------------------------------------------------------


class WaveformPanel(QGroupBox):
    """Waveform-shape picker and square-wave duty-cycle control.

    Emits ``waveform_changed(str)`` with the SCPI shape token
    (``SIN``/``SQU``/``TRI``/``RAMP``/``NOIS``/``DC``) and
    ``duty_cycle_changed(float)`` (percent, SQU only).
    """

    waveform_changed = Signal(str)
    duty_cycle_changed = Signal(float)

    # Display order — most-common first.
    WAVEFORMS = (
        ("SIN",  "Sine"),
        ("SQU",  "Square"),
        ("TRI",  "Triangle"),
        ("RAMP", "Ramp"),
        ("NOIS", "Noise"),
        ("DC",   "DC"),
    )

    def __init__(self, initial: str = "SIN", parent=None):
        super().__init__("Waveform", parent)

        outer = QVBoxLayout(self)
        outer.setSpacing(6)

        # Shape grid: 3×2 of toggle buttons.
        self._shape_buttons: dict[str, QPushButton] = {}
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, (code, label) in enumerate(self.WAVEFORMS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
            )
            btn.clicked.connect(
                lambda _=False, c=code: self._on_shape_clicked(c),
            )
            self._shape_buttons[code] = btn
            grid.addWidget(btn, i // 3, i % 3)
        outer.addLayout(grid)

        # Duty-cycle knob — visible only when SQU is active. Using
        # QLabel + knob so we can label it clearly.
        duty_row = QHBoxLayout()
        duty_row.addWidget(QLabel("Duty:"))
        self._duty_knob = RotaryKnob("Duty")
        self._duty_knob.set_range(20.0, 80.0, 1.0, 50.0)
        self._duty_knob.set_format_func(format_percent)
        self._duty_knob.value_changed.connect(self.duty_cycle_changed.emit)
        duty_row.addWidget(self._duty_knob)
        outer.addLayout(duty_row)

        self._set_active_button(initial)
        self._update_duty_enabled(initial)

    # -- Public API ---------------------------------------------------

    def set_waveform(self, shape: str) -> None:
        shape = shape.upper()
        if shape not in self._shape_buttons:
            return
        self._set_active_button(shape)
        self._update_duty_enabled(shape)

    def set_duty_cycle(self, percent: float) -> None:
        self._duty_knob.blockSignals(True)
        try:
            self._duty_knob.set_value(percent)
        finally:
            self._duty_knob.blockSignals(False)

    # -- Internal -----------------------------------------------------

    def _on_shape_clicked(self, shape: str):
        self._set_active_button(shape)
        self._update_duty_enabled(shape)
        self.waveform_changed.emit(shape)

    def _set_active_button(self, shape: str) -> None:
        for code, btn in self._shape_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(code == shape)
            btn.blockSignals(False)

    def _update_duty_enabled(self, shape: str) -> None:
        # Duty cycle is only meaningful for square — gray it out
        # for every other waveform. Keeps the layout stable (no
        # show/hide jitter) but makes the invalid state visible.
        self._duty_knob.setEnabled(shape == "SQU")
