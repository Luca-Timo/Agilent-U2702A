"""
Agilent 33120A function/arbitrary waveform generator preset.

- Single-channel, 15 MHz sine/square, up to 100 kHz for ramp/triangle
- 50 mVpp to 10 Vpp into 50 Ω (up to 20 Vpp into HiZ)
- Standard SCPI over RS-232 (DB-9); Mac connects via USB-to-RS232 adapter
- Default 9600 8N1 no flow control — matches the instrument's factory
  default. The 33120A's RS-232 baud can be changed from its front
  panel (Utility → I/O → Baud Rate) if a faster link is wanted; update
  this preset accordingly or pass ``baud=...`` to ``LabSession.open``.
"""

from config.instrument_config import (
    FunctionGeneratorConfig,
    SerialConfig,
)


AGILENT_33120A = FunctionGeneratorConfig(
    model="33120A",
    vendor="Agilent",
    num_channels=1,
    serial=SerialConfig(
        baudrate=9600,             # instrument's factory default
        timeout_s=3.0,
        bridge_vid=0x0403,         # FTDI FT232 (most common USB-RS232 chip)
        bridge_pid=0x6001,
    ),
    # usb left at None — 33120A has no direct USB port, only RS-232/GPIB.
    frequency_range=(0.1, 15_000_000.0),   # 0.1 Hz to 15 MHz
    amplitude_range=(0.05, 10.0),          # 50 mVpp to 10 Vpp (into 50 Ω)
    waveforms=("SIN", "SQU", "TRI", "RAMP", "NOIS", "DC"),
)
