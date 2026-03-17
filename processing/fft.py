"""
FFT computation for oscilloscope waveforms.

Functions:
    compute_fft(voltage, time_axis, window)  Single-sided FFT
    magnitude_to_dbv(magnitude, ref)         Convert to dBV scale
"""

import numpy as np


# Available window functions
_WINDOWS = {
    "hann": np.hanning,
    "hamming": np.hamming,
    "blackman": np.blackman,
    "rect": np.ones,
}


def compute_fft(
    voltage: np.ndarray,
    time_axis: np.ndarray,
    window: str = "hann",
) -> tuple[np.ndarray, np.ndarray]:
    """Compute single-sided FFT of a voltage waveform.

    Args:
        voltage: Time-domain voltage array.
        time_axis: Corresponding time axis (seconds).
        window: Window function name ("hann", "hamming", "blackman", "rect").

    Returns:
        (freq_axis, magnitude) where magnitude is in volts (linear).
        freq_axis has N/2 bins from 0 to Nyquist.
    """
    n = len(voltage)
    if n < 2:
        return np.array([0.0]), np.array([0.0])

    # Sample rate from time axis spacing
    dt = time_axis[1] - time_axis[0]
    if dt <= 0:
        return np.array([0.0]), np.array([0.0])
    fs = 1.0 / dt

    # Apply window
    win_func = _WINDOWS.get(window, np.hanning)
    w = win_func(n)
    windowed = voltage * w

    # FFT — single-sided
    spectrum = np.fft.rfft(windowed)
    n_bins = len(spectrum)

    # Magnitude: normalize by window sum for correct amplitude
    win_sum = np.sum(w)
    if win_sum > 0:
        magnitude = 2.0 * np.abs(spectrum) / win_sum
    else:
        magnitude = np.abs(spectrum)
    # DC component should not be doubled
    magnitude[0] /= 2.0

    # Frequency axis
    freq_axis = np.fft.rfftfreq(n, d=dt)

    return freq_axis, magnitude


def magnitude_to_dbv(
    magnitude: np.ndarray,
    ref: float = 1.0,
    floor: float = -120.0,
) -> np.ndarray:
    """Convert linear magnitude to dBV.

    Args:
        magnitude: Linear magnitude array (volts).
        ref: Reference voltage (default 1V for dBV).
        floor: Minimum dB value (clips below this).

    Returns:
        Array of dBV values, clipped at floor.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        dbv = 20.0 * np.log10(magnitude / ref)
    return np.clip(dbv, floor, None)
