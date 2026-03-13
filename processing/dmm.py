"""
DMM-mode stateful measurements — Min/Max/Average tracking.

Operates on NumPy voltage arrays.  Maintains running statistics across
multiple waveform acquisitions per channel.  Call reset() to clear.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional

from processing.measurements import frequency


class DMMMode:
    """Measurement mode constants."""
    DC = "DC"
    AC_RMS = "AC"
    AC_DC_RMS = "AC+DC"


@dataclass
class DMMReading:
    """Snapshot of all DMM values for one channel at one moment."""
    primary: float                  # Main display value (depends on mode)
    mode: str                       # "DC", "AC", or "AC+DC"
    frequency: Optional[float]      # Hz or None
    v_min: float                    # Running minimum of primary
    v_max: float                    # Running maximum of primary
    v_avg: float                    # Running average of primary
    sample_count: int               # Number of frames accumulated
    probe_factor: float             # For display context


class DMMAccumulator:
    """Per-channel running DMM statistics.

    Tracks min/max/average of the *primary* reading across consecutive
    waveform frames.  The primary value depends on the measurement mode:

    - DC:     mean voltage  (Vmean)
    - AC:     AC-coupled RMS  (sqrt(mean((v - dc)²)))
    - AC+DC:  true RMS  (sqrt(mean(v²)))

    This matches real DMM behavior — e.g. Fluke's "Min" in DC mode is
    the minimum DC mean reading, not the minimum instantaneous sample.

    Public API:
        update(voltage, time_axis, probe_factor, mode) -> DMMReading
        reset()
        reading -> Optional[DMMReading]
    """

    def __init__(self):
        self._min: float = float('inf')
        self._max: float = float('-inf')
        self._sum: float = 0.0
        self._count: int = 0
        self._last_reading: Optional[DMMReading] = None

    def update(self, voltage: np.ndarray, time_axis: np.ndarray,
               probe_factor: float = 1.0,
               mode: str = DMMMode.DC) -> DMMReading:
        """Process one waveform frame and return updated reading.

        Args:
            voltage: Scope-space voltage array (before probe factor).
            time_axis: Corresponding time axis.
            probe_factor: Probe attenuation multiplier.
            mode: "DC", "AC", or "AC+DC".

        Returns:
            DMMReading with all current values.
        """
        # Apply probe factor
        v = voltage * probe_factor

        # Compute primary value based on mode
        if mode == DMMMode.DC:
            primary = float(np.mean(v))
        elif mode == DMMMode.AC_RMS:
            dc = float(np.mean(v))
            primary = float(np.sqrt(np.mean((v - dc) ** 2)))
        else:  # AC+DC RMS
            primary = float(np.sqrt(np.mean(v ** 2)))

        # Update running stats
        self._min = min(self._min, primary)
        self._max = max(self._max, primary)
        self._sum += primary
        self._count += 1
        avg = self._sum / self._count

        # Frequency detection
        freq = frequency(v, time_axis)

        self._last_reading = DMMReading(
            primary=primary,
            mode=mode,
            frequency=freq,
            v_min=self._min,
            v_max=self._max,
            v_avg=avg,
            sample_count=self._count,
            probe_factor=probe_factor,
        )
        return self._last_reading

    def reset(self):
        """Clear all accumulated statistics."""
        self._min = float('inf')
        self._max = float('-inf')
        self._sum = 0.0
        self._count = 0
        self._last_reading = None

    @property
    def reading(self) -> Optional[DMMReading]:
        """Last computed reading, or None if no data yet."""
        return self._last_reading
