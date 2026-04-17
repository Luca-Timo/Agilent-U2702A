"""
Scope hardware configuration dataclasses.

Every hardware-dependent value in the codebase is defined here. Supporting
a different oscilloscope is a matter of writing a new preset under
``config/presets/`` and pointing ``config/__init__.py`` at it.

GUI, processing, and instrument modules must never hardcode hardware
constants. Import ``from config import SCOPE`` and read ``SCOPE.<section>.<field>``
instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AdcFormat:
    """Binary waveform payload layout and ADC characteristics."""
    data_offset: int       # header bytes before ADC data in WAV:DATA? response
    data_length: int       # ADC samples per channel per acquisition
    center: int            # mid-scale ADC value (0 V reference)
    range: int             # full ADC span (e.g. 256 for 8-bit unsigned)
    payload_size: int      # total bytes in the binary response


@dataclass(frozen=True)
class GridConfig:
    """Display grid — vertical/horizontal division counts."""
    vertical_divs: int
    horizontal_divs: int


@dataclass(frozen=True)
class UsbIds:
    """USB VID/PID for direct-USB connection (unused on the Mac serial-bridge path)."""
    vid: int
    pid_operational: int
    pid_boot: Optional[int]  # None if the scope has no separate boot-mode firmware


@dataclass(frozen=True)
class SerialConfig:
    """Serial bridge (ESP32-S3 CP2102N) parameters."""
    baudrate: int
    timeout_s: float
    bridge_vid: int        # USB-UART adapter VID (CP2102N = 0x10C4)
    bridge_pid: int        # USB-UART adapter PID (CP2102N = 0xEA60)


@dataclass(frozen=True)
class DemoSignal:
    """Parameters for the DemoBridge synthetic test signal."""
    frequency_hz: float
    duty: float
    high_v: float
    low_v: float
    noise_counts: int


@dataclass(frozen=True)
class ScopeConfig:
    """Complete hardware profile for one oscilloscope model."""
    model: str
    vendor: str
    num_channels: int
    adc: AdcFormat
    grid: GridConfig
    vdiv_values: tuple[float, ...]
    tdiv_values: tuple[float, ...]
    standard_probes: tuple[str, ...]
    custom_probe_range: tuple[float, float]
    usb: UsbIds
    serial: SerialConfig
    demo_signal: DemoSignal
