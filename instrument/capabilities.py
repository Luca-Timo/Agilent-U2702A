"""
Instrument capability declarations.

Each instrument driver exposes a ``Capabilities`` instance so the UI and
automation layer can ask "does this device support triggers / cursors /
FFT / waveform acquisition" without hardcoding ``isinstance`` checks
against driver classes.

This is the single place where we enumerate what a generic lab
instrument can do. Add a new kind here first, then implement drivers
that declare it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class InstrumentKind(str, Enum):
    """Top-level instrument categories."""

    OSCILLOSCOPE = "scope"
    DMM = "dmm"
    FUNCTION_GENERATOR = "funcgen"
    POWER_SUPPLY = "psu"
    ELECTRONIC_LOAD = "eload"
    UNKNOWN = "unknown"


class AcquisitionModel(str, Enum):
    """How this instrument produces data on each acquisition step.

    - ``WAVEFORM``: block of time-series samples per channel per shot
      (scopes). Triggers + cursors + measurements are meaningful.
    - ``SCALAR``: one number per read (DMMs). Min/max/avg tracking is
      meaningful; triggers/cursors are not.
    - ``SETPOINT``: no acquisition — the instrument is an output device
      (func-gens, PSUs). The "acquire" call just reads back the current
      setpoints / status.
    """

    WAVEFORM = "waveform"
    SCALAR = "scalar"
    SETPOINT = "setpoint"


@dataclass(frozen=True)
class Capabilities:
    """Declarative profile of what a driver supports.

    The GUI uses this to decide which panels to show; the automation
    layer uses it to generate introspection output; tests use it as a
    contract check (every capability that's declared True must have a
    corresponding driver method that works headless).
    """

    kind: InstrumentKind
    num_channels: int
    acquisition_model: AcquisitionModel

    # Oscilloscope-ish features
    has_trigger: bool = False
    has_cursors: bool = False
    has_fft: bool = False
    has_math: bool = False

    # Measurement bar — which named measurements this instrument can report.
    # Empty tuple = hide the measurement bar entirely.
    supported_measurements: tuple[str, ...] = ()

    # Output-device features
    has_output_enable: bool = False
    has_sweep: bool = False

    # Free-form tags for future extension without adding bool fields.
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def has_measurements(self) -> bool:
        return bool(self.supported_measurements)


# Convenience presets for the kinds we've designed for. Drivers should
# build on these with dataclasses.replace rather than defining their own
# Capabilities from scratch, so the "what a scope can do" answer lives
# in one place.

OSCILLOSCOPE_DEFAULTS = Capabilities(
    kind=InstrumentKind.OSCILLOSCOPE,
    num_channels=2,
    acquisition_model=AcquisitionModel.WAVEFORM,
    has_trigger=True,
    has_cursors=True,
    has_fft=True,
    has_math=True,
    supported_measurements=(
        "Vpp", "Vmax", "Vmin", "Vrms", "Vmean",
        "Freq", "Period", "Rise", "Fall", "Duty",
    ),
)

DMM_DEFAULTS = Capabilities(
    kind=InstrumentKind.DMM,
    num_channels=1,
    acquisition_model=AcquisitionModel.SCALAR,
)

FUNCGEN_DEFAULTS = Capabilities(
    kind=InstrumentKind.FUNCTION_GENERATOR,
    num_channels=1,
    acquisition_model=AcquisitionModel.SETPOINT,
    has_output_enable=True,
    has_sweep=True,
)
