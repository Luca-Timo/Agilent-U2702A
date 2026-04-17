"""
The ``LayoutFactory`` protocol — the seam MainWindow consumes.

A concrete layout answers five questions:

  1. What goes in the **primary display** area (left-top)?
  2. What **secondary widgets** go underneath it (DMM readout,
     cursor readout, measurement bar)?
  3. What **control panels** stack on the right, in what order?
  4. Which of the above should be **hidden by default** (revealed by
     runtime modes — e.g. DMMWidget stays hidden until DMM mode
     toggles on)?
  5. Which panels are **scope-only** so the MainWindow shell knows
     what to hide when a non-scope mode is entered?

A layout does NOT wire Qt signals — that stays in ``MainWindow`` for
now. Moving slot handlers into per-layout controllers is a follow-up
refactor; the current split only pulls out *which widgets exist*.

Rationale: this is the smallest seam that makes DMMLayout /
FunctionGeneratorLayout implementable without editing MainWindow's
panel-instantiation block. Signal wiring will migrate controller-by-
controller as each new instrument kind lands (see the project memory
file ``project_lab_bench_refactor.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class PanelSpec:
    """One panel in the layout, with placement metadata."""

    # The widget instance (already constructed).
    widget: Any
    # An ``attr`` name — MainWindow sets ``self.<attr> = widget`` so
    # existing slot handlers (``self._channel_panel.foo``) keep working.
    attr: str
    # True to hide the widget initially (e.g. DMMWidget is hidden
    # until the user toggles DMM mode on).
    hidden: bool = False
    # Free-form tags for MainWindow / controllers to find panels by
    # role. "scope_only" means the panel is hidden when DMM mode
    # activates; "display_pane" means it belongs in the left stack;
    # "control_panel" means right stack. A panel can have any number.
    tags: frozenset[str] = field(default_factory=frozenset)
    # Layout stretch factor — 1 means the widget expands to fill,
    # 0 (default) means it takes its natural size.
    stretch: int = 0


@runtime_checkable
class LayoutFactory(Protocol):
    """Contract every concrete layout implements.

    The layout builds its widgets in ``build()`` and returns them
    partitioned into the two columns the MainWindow shell uses.
    """

    def display_widgets(self) -> list[PanelSpec]:
        """Widgets for the left (display) column, top to bottom.

        Typical scope layout: [WaveformContainer, DMMWidget (hidden),
        CursorReadout (hidden), MeasurementBar].
        """

    def control_panels(self) -> list[PanelSpec]:
        """Widgets for the right (control) column, top to bottom.

        Typical scope layout: [UtilityPanel, TimebasePanel, TriggerPanel,
        ChannelPanel, FFTPanel, MathPanel].
        """

    def scope_only_attrs(self) -> tuple[str, ...]:
        """Panel ``attr`` names that should be hidden outside scope modes.

        MainWindow's DMM-mode toggle consults this to decide which
        controls to hide. A DMMLayout would return ``()`` because
        its own panels are always relevant in DMM mode.
        """
