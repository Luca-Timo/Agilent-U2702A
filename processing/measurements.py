"""
Waveform measurements — hardware-independent.

All functions operate on NumPy voltage arrays.
"""

import numpy as np
from typing import Optional


def vpp(voltage: np.ndarray) -> float:
    """Peak-to-peak voltage."""
    return float(np.ptp(voltage))


def vmin(voltage: np.ndarray) -> float:
    """Minimum voltage."""
    return float(np.min(voltage))


def vmax(voltage: np.ndarray) -> float:
    """Maximum voltage."""
    return float(np.max(voltage))


def vrms(voltage: np.ndarray) -> float:
    """RMS voltage (AC+DC)."""
    return float(np.sqrt(np.mean(voltage ** 2)))


def vmean(voltage: np.ndarray) -> float:
    """Mean (DC) voltage."""
    return float(np.mean(voltage))


def frequency(voltage: np.ndarray, time_axis: np.ndarray) -> Optional[float]:
    """Estimate signal frequency via zero-crossing detection.

    Args:
        voltage: Voltage array.
        time_axis: Corresponding time axis.

    Returns:
        Estimated frequency in Hz, or None if cannot determine.
    """
    if len(voltage) < 4:
        return None

    # Remove DC offset
    centered = voltage - np.mean(voltage)

    # Find zero crossings (positive-going)
    crossings = []
    for i in range(len(centered) - 1):
        if centered[i] <= 0 < centered[i + 1]:
            # Linear interpolation for sub-sample accuracy
            frac = -centered[i] / (centered[i + 1] - centered[i])
            t_cross = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            crossings.append(t_cross)

    if len(crossings) < 2:
        return None

    # Average period from consecutive crossings
    periods = np.diff(crossings)
    avg_period = np.mean(periods)

    if avg_period <= 0:
        return None

    return float(1.0 / avg_period)


def period(voltage: np.ndarray, time_axis: np.ndarray) -> Optional[float]:
    """Estimate signal period in seconds.

    Returns:
        Period in seconds, or None if cannot determine.
    """
    freq = frequency(voltage, time_axis)
    if freq is None or freq <= 0:
        return None
    return 1.0 / freq


def compute_all(voltage: np.ndarray, time_axis: np.ndarray) -> dict:
    """Compute all standard measurements.

    Returns:
        Dict with keys: vpp, vmin, vmax, vrms, vmean, frequency, period.
        Values are float or None.
    """
    freq = frequency(voltage, time_axis)
    per = (1.0 / freq) if freq else None

    return {
        "vpp": vpp(voltage),
        "vmin": vmin(voltage),
        "vmax": vmax(voltage),
        "vrms": vrms(voltage),
        "vmean": vmean(voltage),
        "frequency": freq,
        "period": per,
    }
