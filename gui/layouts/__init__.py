"""
Layout factories — pluggable UI templates per instrument kind.

Every instrument kind (scope, DMM, func-gen, …) gets its own layout
class that knows which panels to build and where they go. The
MainWindow shell consumes a layout factory during its ``_setup_ui``;
swapping the active instrument means swapping the layout, not
rewriting MainWindow.

Today only :class:`OscilloscopeLayout` exists. DMMLayout and
FunctionGeneratorLayout will join it as those drivers land.
"""

from gui.layouts.base import LayoutFactory, PanelSpec
from gui.layouts.dmm_layout import DMMLayout
from gui.layouts.funcgen_layout import FunctionGeneratorLayout
from gui.layouts.oscilloscope_layout import OscilloscopeLayout

__all__ = [
    "LayoutFactory", "PanelSpec",
    "OscilloscopeLayout", "DMMLayout", "FunctionGeneratorLayout",
]
