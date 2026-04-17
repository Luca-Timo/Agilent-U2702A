"""
Function-generator layout factory.

Display column:
  - WaveformPreview (analytical, updates on every setpoint change)
  - OutputIndicator (big red/gray button)

Control column:
  - FrequencyPanel
  - AmplitudePanel  (amplitude + offset + load termination)
  - WaveformPanel   (shape picker + duty cycle)

The layout exposes each widget so the window can wire signals in
one place. Future additions (sweep, burst, modulation) land as more
PanelSpecs in ``control_panels()`` — additive change, no shape shift.
"""

from __future__ import annotations

from typing import Optional

from gui.funcgen_panels import AmplitudePanel, FrequencyPanel, WaveformPanel
from gui.layouts.base import LayoutFactory, PanelSpec
from gui.output_indicator import OutputIndicator
from gui.waveform_preview import WaveformPreview


class FunctionGeneratorLayout:
    """Layout factory for function-generator-kind instruments."""

    def __init__(self,
                 *,
                 frequency_range: tuple[float, float] = (0.1, 15_000_000.0),
                 amplitude_range: tuple[float, float] = (0.05, 10.0)):
        self._preview = WaveformPreview()
        self._output_indicator = OutputIndicator()

        min_hz, max_hz = frequency_range
        min_vpp, max_vpp = amplitude_range
        self._frequency_panel = FrequencyPanel(
            min_hz=min_hz, max_hz=max_hz,
            initial_hz=1000.0,
        )
        self._amplitude_panel = AmplitudePanel(
            min_vpp=min_vpp, max_vpp=max_vpp,
            initial_vpp=1.0,
        )
        self._waveform_panel = WaveformPanel(initial="SIN")

    # -- Public accessors (for window signal wiring) -----------------

    @property
    def preview(self) -> WaveformPreview:
        return self._preview

    @property
    def output_indicator(self) -> OutputIndicator:
        return self._output_indicator

    @property
    def frequency_panel(self) -> FrequencyPanel:
        return self._frequency_panel

    @property
    def amplitude_panel(self) -> AmplitudePanel:
        return self._amplitude_panel

    @property
    def waveform_panel(self) -> WaveformPanel:
        return self._waveform_panel

    # -- LayoutFactory protocol --------------------------------------

    def display_widgets(self) -> list[PanelSpec]:
        return [
            PanelSpec(
                widget=self._preview,
                attr="_waveform_preview",
                stretch=1,
                tags=frozenset({"display_pane", "primary_display", "funcgen"}),
            ),
            PanelSpec(
                widget=self._output_indicator,
                attr="_output_indicator",
                stretch=0,
                tags=frozenset({"display_pane", "output_control", "funcgen"}),
            ),
        ]

    def control_panels(self) -> list[PanelSpec]:
        return [
            PanelSpec(
                widget=self._frequency_panel,
                attr="_frequency_panel",
                tags=frozenset({"control_panel", "funcgen"}),
            ),
            PanelSpec(
                widget=self._amplitude_panel,
                attr="_amplitude_panel",
                tags=frozenset({"control_panel", "funcgen"}),
            ),
            PanelSpec(
                widget=self._waveform_panel,
                attr="_waveform_panel",
                tags=frozenset({"control_panel", "funcgen"}),
            ),
        ]

    def scope_only_attrs(self) -> tuple[str, ...]:
        return ()
