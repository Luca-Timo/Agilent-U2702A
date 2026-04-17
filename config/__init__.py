"""
Hardware configuration — single source of truth for all instrument-specific values.

Every supported instrument lives in ``config/presets/`` and registers
itself in :data:`REGISTRY`. The currently active instrument is
:data:`ACTIVE`; the legacy name :data:`SCOPE` aliases it so existing
``from config import SCOPE`` imports keep working.

Adding a new instrument:

1. Write ``config/presets/my_instrument.py`` that builds an
   ``InstrumentConfig`` subclass (``OscilloscopeConfig`` / ``DMMConfig``
   / ``FunctionGeneratorConfig``).
2. Import it below and add it to :data:`REGISTRY`.
3. Write a matching driver in ``instrument/drivers/`` that implements
   the ``InstrumentDriver`` protocol.
4. (For scope/DMM/func-gen specifically:) write a matching
   ``gui/layouts/`` entry so the UI knows how to render it.

Scripts can pick a profile by model name: ``config.get("U2702A")``.
"""

from __future__ import annotations

from config.instrument_config import (
    AdcFormat,
    DemoSignal,
    DMMConfig,
    FunctionGeneratorConfig,
    GridConfig,
    InstrumentConfig,
    OscilloscopeConfig,
    ScopeConfig,       # backwards-compat alias for OscilloscopeConfig
    SerialConfig,
    UsbIds,
)
from config.presets.agilent_33120a import AGILENT_33120A
from config.presets.generic_dmm import GENERIC_DMM
from config.presets.u2702a import U2702A


# Registry of every instrument profile we know about. Keyed by model
# name (as returned by the first field of ``*IDN?``) so
# auto-discovery can look up a profile from the instrument's IDN reply.
REGISTRY: dict[str, InstrumentConfig] = {
    U2702A.model: U2702A,
    GENERIC_DMM.model: GENERIC_DMM,
    AGILENT_33120A.model: AGILENT_33120A,
}


# Active scope profile — change this line (or re-assign at runtime)
# to use a different instrument. Kept as a module-level binding so
# imports of ``SCOPE`` resolve at import time; the lab-bench phases
# will turn this into a per-window binding.
ACTIVE: InstrumentConfig = U2702A

# Legacy alias. The codebase still imports ``SCOPE`` widely; new code
# should prefer ``ACTIVE`` (or ask the driver for its capabilities).
SCOPE: InstrumentConfig = ACTIVE


def get(model: str) -> InstrumentConfig:
    """Look up a registered profile by model name. Raises KeyError."""
    return REGISTRY[model]


def register(config: InstrumentConfig) -> None:
    """Add a profile to the registry at runtime (used by tests / plugins)."""
    REGISTRY[config.model] = config


__all__ = [
    # Active profile + registry
    "ACTIVE",
    "SCOPE",
    "REGISTRY",
    "get",
    "register",
    # Config classes
    "InstrumentConfig",
    "OscilloscopeConfig",
    "ScopeConfig",
    "DMMConfig",
    "FunctionGeneratorConfig",
    # Shared building blocks
    "AdcFormat",
    "GridConfig",
    "UsbIds",
    "SerialConfig",
    "DemoSignal",
]
