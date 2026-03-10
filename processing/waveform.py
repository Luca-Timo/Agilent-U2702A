"""
Waveform data model and ADC-to-voltage conversion.

Hardware-independent: works on raw ADC arrays from any oscilloscope.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class WaveformData:
    """Processed waveform data for one channel."""
    channel: int            # 1..N
    raw_adc: np.ndarray     # uint8 array (1256 points for U2702A)
    voltage: np.ndarray     # float64 voltage array
    time_axis: np.ndarray   # float64 time axis (seconds)
    v_per_div: float        # V/div setting used
    offset: float           # Vertical offset (volts)
    t_per_div: float        # T/div setting used
    probe_factor: float     # Probe attenuation (1 or 10)
    timestamp: float        # time.monotonic() when acquired


# --- U2702A waveform data format ---
# WAV:DATA? returns 2514 bytes:
#   [0:2]     = prefix (01 00)
#   [2:1258]  = CH data (1256 uint8 ADC values)
#   [1258:2514] = padding (zeros)

ADC_DATA_OFFSET = 2
ADC_DATA_LENGTH = 1256
ADC_CENTER = 128
ADC_RANGE = 256
NUM_VERTICAL_DIVS = 8


def parse_wav_data(data: bytes) -> np.ndarray:
    """Extract ADC values from WAV:DATA? binary response.

    Args:
        data: Raw binary payload from the bridge (2514 bytes).

    Returns:
        uint8 array of 1256 ADC values.
    """
    if len(data) < ADC_DATA_OFFSET + ADC_DATA_LENGTH:
        raise ValueError(
            f"WAV:DATA response too short: {len(data)} bytes "
            f"(need {ADC_DATA_OFFSET + ADC_DATA_LENGTH})"
        )
    return np.frombuffer(
        data[ADC_DATA_OFFSET:ADC_DATA_OFFSET + ADC_DATA_LENGTH],
        dtype=np.uint8,
    ).copy()  # copy() to own the memory


def adc_to_voltage(raw: np.ndarray, v_per_div: float,
                   offset: float = 0.0, probe_factor: float = 1.0) -> np.ndarray:
    """Convert raw ADC values to voltage.

    The U2702A uses 8-bit unsigned ADC with center=128=0V.
    Full screen = 8 divisions vertical.

    Formula: (raw - 128) * (8 * v_per_div / 256) * probe_factor + offset

    Args:
        raw: uint8 ADC array.
        v_per_div: Volts per division setting.
        offset: Vertical offset in volts.
        probe_factor: Probe attenuation (1.0 for 1x, 10.0 for 10x).

    Returns:
        float64 voltage array.
    """
    volts_per_count = (NUM_VERTICAL_DIVS * v_per_div) / ADC_RANGE
    return (raw.astype(np.float64) - ADC_CENTER) * volts_per_count * probe_factor + offset


def make_time_axis(num_points: int, t_per_div: float,
                   num_horizontal_divs: int = 10) -> np.ndarray:
    """Create time axis for waveform display.

    10 horizontal divisions, centered at 0.

    Args:
        num_points: Number of data points.
        t_per_div: Time per division in seconds.
        num_horizontal_divs: Number of horizontal divisions (default 10).

    Returns:
        float64 time axis in seconds.
    """
    half_span = (num_horizontal_divs / 2) * t_per_div
    return np.linspace(-half_span, half_span, num_points)
