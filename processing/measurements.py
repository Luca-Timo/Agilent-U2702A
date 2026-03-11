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


def rise_time(voltage: np.ndarray, time_axis: np.ndarray) -> Optional[float]:
    """Measure rise time (10% to 90% of amplitude).

    Finds the first rising transition where the signal crosses from
    below 10% to above 90% of the peak-to-peak amplitude.
    Uses linear interpolation for sub-sample accuracy.

    Returns:
        Rise time in seconds, or None if no complete rising edge found.
    """
    if len(voltage) < 4:
        return None

    v_lo = float(np.min(voltage))
    v_hi = float(np.max(voltage))
    amplitude = v_hi - v_lo
    if amplitude < 1e-9:
        return None

    thresh_10 = v_lo + 0.1 * amplitude
    thresh_90 = v_lo + 0.9 * amplitude

    # Find first rising crossing of 10% threshold
    t10 = None
    i10 = None
    for i in range(len(voltage) - 1):
        if voltage[i] <= thresh_10 < voltage[i + 1]:
            frac = (thresh_10 - voltage[i]) / (voltage[i + 1] - voltage[i])
            t10 = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            i10 = i
            break

    if t10 is None:
        return None

    # Continue scanning for rising crossing of 90% threshold
    for i in range(i10, len(voltage) - 1):
        if voltage[i] <= thresh_90 < voltage[i + 1]:
            frac = (thresh_90 - voltage[i]) / (voltage[i + 1] - voltage[i])
            t90 = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            return float(t90 - t10)

    return None


def fall_time(voltage: np.ndarray, time_axis: np.ndarray) -> Optional[float]:
    """Measure fall time (90% to 10% of amplitude).

    Finds the first falling transition where the signal crosses from
    above 90% to below 10% of the peak-to-peak amplitude.
    Uses linear interpolation for sub-sample accuracy.

    Returns:
        Fall time in seconds, or None if no complete falling edge found.
    """
    if len(voltage) < 4:
        return None

    v_lo = float(np.min(voltage))
    v_hi = float(np.max(voltage))
    amplitude = v_hi - v_lo
    if amplitude < 1e-9:
        return None

    thresh_10 = v_lo + 0.1 * amplitude
    thresh_90 = v_lo + 0.9 * amplitude

    # Find first falling crossing of 90% threshold
    t90 = None
    i90 = None
    for i in range(len(voltage) - 1):
        if voltage[i] >= thresh_90 > voltage[i + 1]:
            frac = (voltage[i] - thresh_90) / (voltage[i] - voltage[i + 1])
            t90 = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            i90 = i
            break

    if t90 is None:
        return None

    # Continue scanning for falling crossing of 10% threshold
    for i in range(i90, len(voltage) - 1):
        if voltage[i] >= thresh_10 > voltage[i + 1]:
            frac = (voltage[i] - thresh_10) / (voltage[i] - voltage[i + 1])
            t10 = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            return float(t10 - t90)

    return None


def duty_cycle(voltage: np.ndarray, time_axis: np.ndarray) -> Optional[float]:
    """Measure duty cycle as a percentage.

    Uses the 50% amplitude threshold (midpoint between min and max).
    Finds one complete cycle via two positive-going crossings, then
    measures the fraction of time the signal is above the midpoint.

    Returns:
        Duty cycle as percentage (0-100), or None if cannot determine.
    """
    if len(voltage) < 4:
        return None

    v_lo = float(np.min(voltage))
    v_hi = float(np.max(voltage))
    amplitude = v_hi - v_lo
    if amplitude < 1e-9:
        return None

    v_mid = (v_lo + v_hi) / 2.0

    # Find positive-going crossings of midpoint
    pos_crossings = []
    for i in range(len(voltage) - 1):
        if voltage[i] <= v_mid < voltage[i + 1]:
            frac = (v_mid - voltage[i]) / (voltage[i + 1] - voltage[i])
            t_cross = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            pos_crossings.append((i, t_cross))
        if len(pos_crossings) >= 2:
            break

    if len(pos_crossings) < 2:
        return None

    i_start, t_pos1 = pos_crossings[0]
    i_end, t_pos2 = pos_crossings[1]
    cycle_period = t_pos2 - t_pos1

    if cycle_period <= 0:
        return None

    # Find the negative-going crossing between the two positive crossings
    for i in range(i_start, i_end + 1):
        if i >= len(voltage) - 1:
            break
        if voltage[i] >= v_mid > voltage[i + 1]:
            frac = (voltage[i] - v_mid) / (voltage[i] - voltage[i + 1])
            t_neg = time_axis[i] + frac * (time_axis[i + 1] - time_axis[i])
            high_time = t_neg - t_pos1
            return float(high_time / cycle_period * 100.0)

    return None


def compute_all(voltage: np.ndarray, time_axis: np.ndarray) -> dict:
    """Compute all standard measurements.

    Returns:
        Dict with keys: vpp, vmin, vmax, vrms, vmean, frequency, period,
        rise_time, fall_time, duty_cycle.
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
        "rise_time": rise_time(voltage, time_axis),
        "fall_time": fall_time(voltage, time_axis),
        "duty_cycle": duty_cycle(voltage, time_axis),
    }
