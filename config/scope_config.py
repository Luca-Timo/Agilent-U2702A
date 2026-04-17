"""
Backwards-compatibility shim.

The authoritative definitions moved to ``config.instrument_config`` when
the codebase grew to support multiple instrument kinds. This module
re-exports the scope-relevant types so older imports keep resolving.
New code should import from ``config`` or ``config.instrument_config``.
"""

from config.instrument_config import (  # noqa: F401
    AdcFormat,
    DemoSignal,
    GridConfig,
    OscilloscopeConfig,
    ScopeConfig,
    SerialConfig,
    UsbIds,
)
