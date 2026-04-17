"""
DMM layout factory — UI for multimeter-kind instruments.

Reuses ``DMMWidget`` (which the scope's DMM mode already uses) so
the display looks identical whether the DMM mode is running against
the scope or against a standalone DMM. Control panels are minimal:
mode selection is the primary control; the big-digit display takes
most of the screen.

Today this layout isn't wired into MainWindow — MainWindow hardcodes
OscilloscopeLayout. The piece that picks a layout at runtime (based
on the connected driver's Capabilities.kind) lands in a follow-up
commit once we have a real DMM to switch to. The layout factory is
complete on its own and is already testable.
"""

from __future__ import annotations

from typing import Optional

from gui.dmm_widget import DMMWidget
from gui.layouts.base import LayoutFactory, PanelSpec


class DMMLayout:
    """Layout factory for DMM-kind instruments.

    Display: single ``DMMWidget`` (big-digit readout, mode buttons,
    reset-stats button, min/max/avg row).

    Control panels: none for now — the DMMWidget itself carries the
    mode selector and reset button. Future additions (range override,
    integration time, dual-display) will slot in here as PanelSpecs.
    """

    def __init__(self, num_channels: int = 1):
        self._num_channels = num_channels
        self._dmm_widget = DMMWidget(num_channels=num_channels)

    # -- Public accessors (for signal wiring from the controller) ---

    @property
    def dmm_widget(self) -> DMMWidget:
        return self._dmm_widget

    # -- LayoutFactory protocol --------------------------------------

    def display_widgets(self) -> list[PanelSpec]:
        return [
            PanelSpec(
                widget=self._dmm_widget,
                attr="_dmm_widget",
                stretch=1,
                tags=frozenset({"display_pane", "primary_display", "dmm"}),
            ),
        ]

    def control_panels(self) -> list[PanelSpec]:
        # Minimal — DMMWidget owns its own mode buttons. Panel slot is
        # reserved for future range/integration-time/averaging controls.
        return []

    def scope_only_attrs(self) -> tuple[str, ...]:
        return ()
