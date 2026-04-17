"""
Agilent U2702A hardware profile.

- 2-channel, 200 MHz USB-powered PC oscilloscope
- 8-bit unsigned ADC, 1256 samples per acquisition, center = 128 = 0 V
- 8 vertical divisions, 10 horizontal divisions
- Reached over an ESP32-S3 serial bridge (see ``instrument/serial_bridge.py``)
"""

from config.instrument_config import (
    AdcFormat,
    DemoSignal,
    GridConfig,
    OscilloscopeConfig,
    SerialConfig,
    UsbIds,
)


U2702A = OscilloscopeConfig(
    model="U2702A",
    vendor="Agilent",
    num_channels=2,
    serial=SerialConfig(
        baudrate=2_000_000,
        timeout_s=5.0,
        bridge_vid=0x10C4,         # Silicon Labs CP2102N
        bridge_pid=0xEA60,
    ),
    usb=UsbIds(
        vid=0x0957,                # Agilent/Keysight
        pid_operational=0x2918,    # Normal USBTMC mode
        pid_boot=0x2818,           # Firmware-update mode
    ),
    adc=AdcFormat(
        data_offset=2,             # 2-byte prefix (01 00)
        data_length=1256,          # samples per channel
        center=128,                # ADC 128 = 0 V
        range=256,                 # 8-bit unsigned
        payload_size=2514,         # 2 prefix + 1256 CH data + 1256 padding
    ),
    grid=GridConfig(
        vertical_divs=8,
        horizontal_divs=10,
    ),
    vdiv_values=(
        0.002, 0.005,
        0.010, 0.020, 0.050,
        0.100, 0.200, 0.500,
        1.000, 2.000, 5.000,
        10.00,
    ),
    tdiv_values=(
        5e-9, 10e-9, 20e-9, 50e-9,
        100e-9, 200e-9, 500e-9,
        1e-6, 2e-6, 5e-6,
        10e-6, 20e-6, 50e-6,
        100e-6, 200e-6, 500e-6,
        1e-3, 2e-3, 5e-3,
        10e-3, 20e-3, 50e-3,
        100e-3, 200e-3, 500e-3,
        1.0, 2.0, 5.0,
        10.0, 20.0, 50.0,
    ),
    standard_probes=("1x", "10x", "20x", "50x", "100x"),
    custom_probe_range=(0.001, 10000.0),
    demo_signal=DemoSignal(
        frequency_hz=1000.0,
        duty=0.5,
        high_v=3.3,
        low_v=0.0,
        noise_counts=1,
    ),
)
