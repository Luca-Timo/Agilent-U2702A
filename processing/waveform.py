"""
Waveform data model and ADC-to-voltage conversion.

All hardware specifics (ADC format, vertical/horizontal div counts) are
read from ``config.SCOPE``. The logic itself is hardware-independent.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from config import SCOPE


@dataclass
class WaveformData:
    """Processed waveform data for one channel."""
    channel: int            # 1..N
    raw_adc: np.ndarray     # uint8 array (SCOPE.adc.data_length points)
    voltage: np.ndarray     # float64 voltage array
    time_axis: np.ndarray   # float64 time axis (seconds)
    v_per_div: float        # V/div setting used
    offset: float           # Vertical offset (volts)
    t_per_div: float        # T/div setting used
    probe_factor: float     # Probe attenuation (1 or 10)
    timestamp: float        # time.monotonic() when acquired
    trigger_sample: Optional[int] = None   # Sample index where trigger crossed

    # Lazily-computed measurement cache (see ``measurements`` property).
    _cached_measurements: Optional[dict] = field(
        default=None, init=False, repr=False, compare=False,
    )

    @property
    def measurements(self) -> dict:
        """Return cached ``processing.measurements.compute_all`` output.

        Computed once on first access, then memoised. Readers can call
        this from any number of places per frame without re-running the
        full measurement pipeline.
        """
        if self._cached_measurements is None:
            # Local import to avoid circular import at module load
            from processing import measurements as _meas
            self._cached_measurements = _meas.compute_all(
                self.voltage, self.time_axis,
            )
        return self._cached_measurements


def parse_wav_data(data: bytes) -> np.ndarray:
    """Extract ADC values from WAV:DATA? binary response.

    Args:
        data: Raw binary payload from the bridge (``SCOPE.adc.payload_size`` bytes).

    Returns:
        uint8 array of ``SCOPE.adc.data_length`` ADC values.
    """
    adc = SCOPE.adc
    if len(data) < adc.data_offset + adc.data_length:
        raise ValueError(
            f"WAV:DATA response too short: {len(data)} bytes "
            f"(need {adc.data_offset + adc.data_length})"
        )
    return np.frombuffer(
        data[adc.data_offset:adc.data_offset + adc.data_length],
        dtype=np.uint8,
    ).copy()  # copy() to own the memory


def adc_to_voltage(raw: np.ndarray, v_per_div: float,
                   offset: float = 0.0) -> np.ndarray:
    """Convert raw ADC values to scope-space voltage.

    Uses ADC format from ``SCOPE.adc`` and grid geometry from ``SCOPE.grid``.

    Returns voltage as measured by the scope (at the BNC input).
    Probe attenuation is handled separately in the display layer
    to avoid double-application with the scope's own scaling.

    Formula: ``(raw - center) * (vertical_divs * v_per_div / range) + offset``
    """
    adc = SCOPE.adc
    grid = SCOPE.grid
    volts_per_count = (grid.vertical_divs * v_per_div) / adc.range
    return (raw.astype(np.float64) - adc.center) * volts_per_count + offset


# Module-level cached index array for time-axis construction.
# Reused across frames since the ADC sample count is fixed per scope.
_TIME_INDEX_CACHE: np.ndarray = np.arange(SCOPE.adc.data_length, dtype=np.float64)


def make_time_axis(num_points: int, t_per_div: float,
                   num_horizontal_divs: Optional[int] = None,
                   trigger_sample: Optional[int] = None) -> np.ndarray:
    """Create time axis for waveform display.

    If ``trigger_sample`` is given, that sample is placed at time=0;
    otherwise the center of the array is at time=0.

    Args:
        num_points: Number of data points.
        t_per_div: Time per division in seconds.
        num_horizontal_divs: Horizontal divisions (defaults to ``SCOPE.grid.horizontal_divs``).
        trigger_sample: Sample index where trigger occurred (time=0).
            If None, center of array is used.

    Returns:
        float64 time axis in seconds.
    """
    if num_horizontal_divs is None:
        num_horizontal_divs = SCOPE.grid.horizontal_divs

    total_span = num_horizontal_divs * t_per_div
    dt = total_span / num_points

    if trigger_sample is None:
        trigger_sample = num_points // 2

    # time=0 at trigger_sample, negative before, positive after.
    # Reuse the cached index array when num_points matches the configured
    # ADC length (the common hot-path case); fall back to np.arange otherwise.
    if num_points == _TIME_INDEX_CACHE.shape[0]:
        idx = _TIME_INDEX_CACHE
    else:
        idx = np.arange(num_points, dtype=np.float64)
    return (idx - trigger_sample) * dt


def find_trigger_crossing(voltage: np.ndarray, level: float,
                          slope: str = "POS",
                          search_center: int | None = None,
                          search_radius: int | None = None) -> int | None:
    """Find the sample index where the signal crosses the trigger level.

    Searches for the crossing nearest to the center of the buffer
    (or search_center if given).

    Args:
        voltage: Voltage array.
        level: Trigger level in volts.
        slope: "POS" for rising edge, "NEG" for falling edge.
        search_center: Center of search region (default: array midpoint).
        search_radius: Search ± this many samples from center (default: half array).

    Returns:
        Sample index of the trigger crossing, or None if not found.
    """
    n = len(voltage)
    if n < 2:
        return None

    if search_center is None:
        search_center = n // 2
    if search_radius is None:
        search_radius = n // 2

    lo = max(0, search_center - search_radius)
    hi = min(n - 1, search_center + search_radius)

    best_idx = None
    best_dist = n  # distance from search_center

    for i in range(lo, hi):
        if slope == "POS":
            # Rising edge: voltage[i] <= level < voltage[i+1]
            if voltage[i] <= level < voltage[i + 1]:
                dist = abs(i - search_center)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
        elif slope == "NEG":
            # Falling edge: voltage[i] >= level > voltage[i+1]
            if voltage[i] >= level > voltage[i + 1]:
                dist = abs(i - search_center)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
        else:
            # Either edge
            crosses_up = voltage[i] <= level < voltage[i + 1]
            crosses_down = voltage[i] >= level > voltage[i + 1]
            if crosses_up or crosses_down:
                dist = abs(i - search_center)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i

    return best_idx
