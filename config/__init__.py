"""
Hardware configuration — single source of truth for all scope-specific values.

Swap the line below (``SCOPE = ...``) to point at a different preset to
support a different oscilloscope. GUI/processing code should only ever read
``SCOPE.<section>.<field>``; it must not hardcode hardware values anywhere.
"""

from config.scope_config import (
    AdcFormat,
    DemoSignal,
    GridConfig,
    ScopeConfig,
    SerialConfig,
    UsbIds,
)
from config.presets.u2702a import U2702A


# Active scope profile — change this line to support a different scope.
SCOPE: ScopeConfig = U2702A


__all__ = [
    "SCOPE",
    "ScopeConfig",
    "AdcFormat",
    "GridConfig",
    "UsbIds",
    "SerialConfig",
    "DemoSignal",
]
