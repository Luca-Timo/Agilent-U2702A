"""
Generic SCPI DMM preset.

Placeholder profile that works with ``GenericDMMDriver`` against any
DMM implementing the standard ``MEAS:*?`` commands. Swap in a
model-specific preset (ranges, digit count, accuracy specs) when
adding a real DMM to the registry.
"""

from config.instrument_config import DMMConfig, SerialConfig


GENERIC_DMM = DMMConfig(
    model="Generic-DMM",
    vendor="SCPI",
    num_channels=1,
    serial=SerialConfig(
        baudrate=115200,           # reasonable default; override per model
        timeout_s=3.0,
        bridge_vid=0x10C4,         # CP2102N if going via the same ESP32 bridge
        bridge_pid=0xEA60,
    ),
    # Capability placeholders — a real preset would populate these.
    measurement_modes=("DCV", "ACV", "DCI", "ACI", "RES", "FREQ", "CAP", "TEMP"),
    voltage_ranges=("AUTO", "100mV", "1V", "10V", "100V", "1000V"),
    current_ranges=("AUTO", "10mA", "100mA", "1A", "10A"),
    resistance_ranges=("AUTO", "100Ω", "1kΩ", "10kΩ", "100kΩ", "1MΩ", "10MΩ"),
    display_digits=5,
)
