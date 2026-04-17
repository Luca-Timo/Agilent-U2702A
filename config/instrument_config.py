"""
Instrument configuration hierarchy.

Every supported instrument model has a frozen ``InstrumentConfig``
instance with all of its hardware-specific values. The active profile
is selected in ``config/__init__.py``. Adding a new instrument is
writing a new preset file and registering it here — nothing else
(ideally) needs to change.

Structure:

    InstrumentConfig            (base: model, vendor, num_channels, serial, usb)
     ├── OscilloscopeConfig     (adc, grid, vdiv/tdiv, probes, demo_signal)
     ├── DMMConfig              (ranges, digits, measurement modes)   [placeholder]
     └── FunctionGeneratorConfig (frequency/amplitude ranges, waveforms) [placeholder]

The DMM and function-generator configs are placeholders for the
future lab-bench expansion — they document the shape we'll need when
adding those instrument types, but no driver uses them yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class UsbIds:
    """USB VID/PID for direct-USB connection."""

    vid: int
    pid_operational: int
    # ``None`` when the instrument has no separate firmware-update mode.
    pid_boot: Optional[int] = None


@dataclass(frozen=True)
class SerialConfig:
    """USB-to-serial bridge parameters (ESP32-S3 / CP2102N path)."""

    baudrate: int
    timeout_s: float
    bridge_vid: int
    bridge_pid: int


# ---------------------------------------------------------------------
# Base class — every instrument has these
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class InstrumentConfig:
    """Fields every instrument profile must provide."""

    model: str
    vendor: str
    num_channels: int
    serial: SerialConfig
    usb: Optional[UsbIds] = None

    # Pretty name for menus / dialogs.
    @property
    def display_name(self) -> str:
        return f"{self.vendor} {self.model}"


# ---------------------------------------------------------------------
# Oscilloscope
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class AdcFormat:
    """Binary waveform payload layout and ADC characteristics."""

    data_offset: int       # header bytes before ADC data in WAV:DATA? response
    data_length: int       # ADC samples per channel per acquisition
    center: int            # mid-scale ADC value (0 V reference)
    range: int             # full ADC span
    payload_size: int      # total bytes in the binary response


@dataclass(frozen=True)
class GridConfig:
    """Display grid — vertical/horizontal division counts."""

    vertical_divs: int
    horizontal_divs: int


@dataclass(frozen=True)
class DemoSignal:
    """Parameters for the DemoBridge synthetic test signal."""

    frequency_hz: float
    duty: float
    high_v: float
    low_v: float
    noise_counts: int


@dataclass(frozen=True)
class OscilloscopeConfig(InstrumentConfig):
    """Oscilloscope-specific hardware profile."""

    adc: AdcFormat = None  # type: ignore[assignment]
    grid: GridConfig = None  # type: ignore[assignment]
    vdiv_values: tuple[float, ...] = ()
    tdiv_values: tuple[float, ...] = ()
    standard_probes: tuple[str, ...] = ()
    custom_probe_range: tuple[float, float] = (0.001, 10_000.0)
    demo_signal: Optional[DemoSignal] = None


# ---------------------------------------------------------------------
# DMM — placeholder for future expansion
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class DMMConfig(InstrumentConfig):
    """Digital multimeter hardware profile (future)."""

    measurement_modes: tuple[str, ...] = (
        "DCV", "ACV", "DCI", "ACI", "RES", "FREQ", "CAP", "TEMP",
    )
    voltage_ranges: tuple[str, ...] = ()
    current_ranges: tuple[str, ...] = ()
    resistance_ranges: tuple[str, ...] = ()
    display_digits: int = 4  # 4.5, 5.5, 6.5 digit DMMs


# ---------------------------------------------------------------------
# Function generator — placeholder for future expansion
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class FunctionGeneratorConfig(InstrumentConfig):
    """Arbitrary / function generator hardware profile (future)."""

    frequency_range: tuple[float, float] = (0.0, 0.0)
    amplitude_range: tuple[float, float] = (0.0, 0.0)
    waveforms: tuple[str, ...] = ("SIN", "SQU", "RAMP", "PULSE", "NOISE", "ARB")


# ---------------------------------------------------------------------
# Backwards-compatibility: ``ScopeConfig`` remains a usable alias so the
# existing preset file (config/presets/u2702a.py) and every call site
# that types ``ScopeConfig`` explicitly keeps working.
# ---------------------------------------------------------------------

ScopeConfig = OscilloscopeConfig
