"""
Software autoscale — pick best V/div, T/div, and offset for the current signal.

The U2702A has no SCPI autoscale command, so this is done entirely in software
using the most recent waveform data.  All functions are pure computation with
no GUI imports — value lists are passed as arguments.
"""

from typing import Optional

import numpy as np


# Target: signal fills ~6 of 8 vertical divisions (75%)
TARGET_FILL_DIVS = 6.0


def pick_vdiv(signal_vpp: float, vdiv_values: list[float],
              target_divs: float = TARGET_FILL_DIVS) -> float:
    """Pick the best V/div so signal_vpp fills *target_divs* divisions.

    Walks the sorted 1-2-5 sequence and picks the smallest V/div
    where the signal fits within *target_divs* divisions.

    Args:
        signal_vpp: Peak-to-peak voltage of the signal.
        vdiv_values: Sorted list of available V/div values (ascending).
        target_divs: How many of 8 divisions the signal should fill.

    Returns:
        Best V/div from *vdiv_values*.
    """
    if signal_vpp <= 0 or len(vdiv_values) == 0:
        return vdiv_values[len(vdiv_values) // 2] if vdiv_values else 1.0

    ideal = signal_vpp / target_divs

    for v in vdiv_values:
        if v >= ideal:
            return v

    # Signal too large for any setting — use maximum
    return vdiv_values[-1]


def pick_tdiv(freq: Optional[float], tdiv_values: list[float],
              target_cycles: float = 2.5) -> Optional[float]:
    """Pick T/div to show *target_cycles* complete cycles on 10 divisions.

    Args:
        freq: Signal frequency in Hz, or None if unknown.
        tdiv_values: Sorted list of available T/div values (ascending).
        target_cycles: How many complete cycles to show (default 2.5).

    Returns:
        Best T/div from *tdiv_values*, or None if freq is unknown.
    """
    if freq is None or freq <= 0 or len(tdiv_values) == 0:
        return None

    # total_time = target_cycles / freq; t_per_div = total_time / 10
    ideal = (target_cycles / freq) / 10.0

    for t in tdiv_values:
        if t >= ideal:
            return t

    return tdiv_values[-1]


def compute_center_offset(voltage: np.ndarray) -> float:
    """Compute the vertical offset that centers the signal on screen.

    Returns the negative of the signal's midpoint so that the center
    of the waveform aligns with the display center (0 V line).
    """
    v_min = float(np.min(voltage))
    v_max = float(np.max(voltage))
    midpoint = (v_min + v_max) / 2.0
    return -midpoint
