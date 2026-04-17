"""
Oscilloscope layout factory — current scope UI as a pluggable template.

This class builds exactly the widgets MainWindow used to construct
inline; the attr names match the old ``self._<panel>`` bindings so
every downstream slot handler, session save/restore, and export
context keeps working unchanged.

Swapping to a DMMLayout later means writing a sibling class that
returns different PanelSpecs — no MainWindow edits.
"""

from __future__ import annotations

from typing import Optional

from config import SCOPE

from gui.channel_panel import ChannelPanel
from gui.cursor_readout import CursorReadout
from gui.dmm_widget import DMMWidget
from gui.fft_panel import FFTPanel
from gui.layouts.base import LayoutFactory, PanelSpec
from gui.math_panel import MathPanel
from gui.measurement_bar import MeasurementBar
from gui.timebase_panel import TimebasePanel
from gui.trigger_panel import TriggerPanel
from gui.utility_panel import UtilityPanel
from gui.waveform_container import WaveformContainer


class OscilloscopeLayout:
    """Layout factory for oscilloscope mode.

    Emits the same widget set the pre-refactor MainWindow constructed
    inline. The display order (waveform → DMM → cursor readout →
    measurement bar, then the six right-hand panels) is preserved
    byte-for-byte.
    """

    def __init__(self, num_channels: Optional[int] = None):
        self._num_channels = (
            num_channels if num_channels is not None else SCOPE.num_channels
        )

        # Build the widgets eagerly so the factory can be queried
        # multiple times (display_widgets / control_panels / test
        # assertions) and get the same objects every time.
        self._container = WaveformContainer(num_channels=self._num_channels)
        self._dmm_widget = DMMWidget(num_channels=self._num_channels)
        self._cursor_readout = CursorReadout()
        self._measurement_bar = MeasurementBar(num_channels=self._num_channels)

        self._utility_panel = UtilityPanel()
        self._utility_panel.set_autoscale_enabled(False)
        self._timebase_panel = TimebasePanel()
        self._trigger_panel = TriggerPanel(num_channels=self._num_channels)
        self._channel_panel = ChannelPanel(num_channels=self._num_channels)
        self._fft_panel = FFTPanel()
        self._math_panel = MathPanel()

    # -- LayoutFactory protocol --------------------------------------

    def display_widgets(self) -> list[PanelSpec]:
        return [
            PanelSpec(
                widget=self._container,
                attr="_container",
                stretch=1,
                tags=frozenset({"display_pane", "primary_display"}),
            ),
            PanelSpec(
                widget=self._dmm_widget,
                attr="_dmm_widget",
                stretch=1,
                hidden=True,   # revealed when DMM mode activates
                tags=frozenset({"display_pane", "dmm_display"}),
            ),
            PanelSpec(
                widget=self._cursor_readout,
                attr="_cursor_readout",
                hidden=True,   # revealed when cursors activate
                tags=frozenset({"display_pane", "cursor_readout"}),
            ),
            PanelSpec(
                widget=self._measurement_bar,
                attr="_measurement_bar",
                tags=frozenset({"display_pane", "measurements"}),
            ),
        ]

    def control_panels(self) -> list[PanelSpec]:
        return [
            PanelSpec(
                widget=self._utility_panel,
                attr="_utility_panel",
                tags=frozenset({"control_panel"}),
            ),
            PanelSpec(
                widget=self._timebase_panel,
                attr="_timebase_panel",
                tags=frozenset({"control_panel", "scope_only"}),
            ),
            PanelSpec(
                widget=self._trigger_panel,
                attr="_trigger_panel",
                tags=frozenset({"control_panel", "scope_only"}),
            ),
            PanelSpec(
                widget=self._channel_panel,
                attr="_channel_panel",
                tags=frozenset({"control_panel"}),
            ),
            PanelSpec(
                widget=self._fft_panel,
                attr="_fft_panel",
                tags=frozenset({"control_panel"}),
            ),
            PanelSpec(
                widget=self._math_panel,
                attr="_math_panel",
                tags=frozenset({"control_panel"}),
            ),
        ]

    def scope_only_attrs(self) -> tuple[str, ...]:
        return ("_timebase_panel", "_trigger_panel")
