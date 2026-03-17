"""
Channel math operations for oscilloscope waveforms.

All functions operate on raw NumPy arrays and are hardware-independent.
"""

import numpy as np


def channel_add(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """CH1 + CH2."""
    n = min(len(v1), len(v2))
    return v1[:n] + v2[:n]


def channel_subtract(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """CH1 - CH2."""
    n = min(len(v1), len(v2))
    return v1[:n] - v2[:n]


def channel_multiply(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """CH1 * CH2."""
    n = min(len(v1), len(v2))
    return v1[:n] * v2[:n]


def channel_divide(
    v1: np.ndarray,
    v2: np.ndarray,
    epsilon: float = 1e-12,
) -> np.ndarray:
    """CH1 / CH2 with zero protection.

    Where |v2| < epsilon, result is 0.
    """
    n = min(len(v1), len(v2))
    a, b = v1[:n], v2[:n]
    result = np.zeros_like(a)
    mask = np.abs(b) >= epsilon
    result[mask] = a[mask] / b[mask]
    return result


def channel_invert(voltage: np.ndarray) -> np.ndarray:
    """Negate voltage (invert channel)."""
    return -voltage


# Operation dispatch table
MATH_OPS = {
    "add": channel_add,
    "sub": channel_subtract,
    "mul": channel_multiply,
    "div": channel_divide,
}
