"""
Typed acquisition results — what a driver ``acquire()`` call returns.

Each instrument kind produces a different shape of per-step data:

    AcquisitionResult  (Protocol)
     ├── WaveformData        ← oscilloscope (processing/waveform.py)
     ├── MeterReading        ← DMM           [placeholder]
     └── GeneratorState      ← function generator / PSU / eload  [placeholder]

MainWindow / automation callers can dispatch on type or on the
``kind`` attribute. The placeholder classes document the shape the
DMM / func-gen drivers will emit when those phases land; none of the
current code path uses them yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class AcquisitionResult(Protocol):
    """What every driver's ``acquire()`` method returns (one per result).

    Drivers may emit multiple results per acquisition step (e.g. a
    4-channel scope returns four ``WaveformData`` objects); each one
    satisfies this protocol.
    """

    kind: str                 # "waveform" | "scalar" | "setpoint"
    timestamp: float          # time.monotonic() when acquired
    channel: int              # 1-based; virtual channels (MATH) get a high id
    metadata: dict            # free-form; driver-specific


@dataclass
class MeterReading:
    """Scalar reading from a DMM-like instrument.

    Placeholder for the DMM phase — not emitted today. When the DMM
    driver lands, ``DMMDriver.acquire()`` returns a ``MeterReading``
    per read, the GUI shows the big-digit display, measurements bar is
    hidden (Capabilities.has_measurements is False), and cursors are
    hidden (Capabilities.has_cursors is False).
    """

    channel: int
    primary: float                 # the headline value the UI displays
    unit: str                      # "V", "A", "Ω", "Hz", "F", "°C", etc.
    timestamp: float
    # Secondary tracking values updated by the driver over time
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    average: Optional[float] = None
    samples: int = 1
    # Range the reading was taken on ("100mV", "AUTO", etc.) — displayed
    # in the GUI's secondary row.
    range: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    kind: str = "scalar"


@dataclass
class GeneratorState:
    """Output-device state read-back (function-gen / PSU / eload).

    Placeholder for the func-gen phase. The driver fills this from a
    state query each tick; the UI reflects output on/off and the active
    setpoints without doing any ADC parsing.
    """

    channel: int
    output_enabled: bool
    timestamp: float
    # Arbitrary setpoint map — e.g. {"frequency": 1_000.0, "amplitude": 2.0,
    # "waveform": "SIN", "offset": 0.0, "phase": 0.0}
    setpoints: dict[str, Any] = field(default_factory=dict)
    # Measured / reported values (if the instrument reports back) —
    # e.g. PSU actual voltage/current.
    readback: dict[str, Any] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    kind: str = "setpoint"
