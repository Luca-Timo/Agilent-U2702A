"""
Software autoscale — pick best V/div, T/div, and offset for the current signal.

The U2702A has no SCPI autoscale command, so this is done entirely in software
using the most recent waveform data.  All functions are pure computation with
no GUI imports — value lists are passed as arguments.

Division counts default to ``SCOPE.grid`` but can be overridden for testing
or alternative display geometries.
"""

from typing import Optional

import numpy as np

from config import SCOPE


# Default: signal should fill ~75% of the available vertical divisions.
DEFAULT_FILL_FRACTION = 0.75


def pick_vdiv(signal_vpp: float, vdiv_values: list[float],
              target_divs: Optional[float] = None,
              vertical_divs: Optional[int] = None) -> float:
    """Pick the best V/div so signal_vpp fills *target_divs* divisions.

    Walks the sorted 1-2-5 sequence and picks the smallest V/div
    where the signal fits within *target_divs* divisions.

    Args:
        signal_vpp: Peak-to-peak voltage of the signal.
        vdiv_values: Sorted list of available V/div values (ascending).
        target_divs: Division fill target (defaults to
            ``DEFAULT_FILL_FRACTION * vertical_divs``).
        vertical_divs: Grid height (defaults to ``SCOPE.grid.vertical_divs``).

    Returns:
        Best V/div from *vdiv_values*.
    """
    if vertical_divs is None:
        vertical_divs = SCOPE.grid.vertical_divs
    if target_divs is None:
        target_divs = DEFAULT_FILL_FRACTION * vertical_divs
    if signal_vpp <= 0 or len(vdiv_values) == 0:
        return vdiv_values[len(vdiv_values) // 2] if vdiv_values else 1.0

    ideal = signal_vpp / target_divs

    for v in vdiv_values:
        if v >= ideal:
            return v

    # Signal too large for any setting — use maximum
    return vdiv_values[-1]


def pick_tdiv(freq: Optional[float], tdiv_values: list[float],
              target_cycles: float = 2.5,
              horizontal_divs: Optional[int] = None) -> Optional[float]:
    """Pick T/div to show ``target_cycles`` complete cycles across the screen.

    Args:
        freq: Signal frequency in Hz, or None if unknown.
        tdiv_values: Sorted list of available T/div values (ascending).
        target_cycles: How many complete cycles to show (default 2.5).
        horizontal_divs: Grid width (defaults to ``SCOPE.grid.horizontal_divs``).

    Returns:
        Best T/div from *tdiv_values*, or None if freq is unknown.
    """
    if horizontal_divs is None:
        horizontal_divs = SCOPE.grid.horizontal_divs
    if freq is None or freq <= 0 or len(tdiv_values) == 0:
        return None

    # total_time = target_cycles / freq; t_per_div = total_time / horizontal_divs
    ideal = (target_cycles / freq) / horizontal_divs

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
