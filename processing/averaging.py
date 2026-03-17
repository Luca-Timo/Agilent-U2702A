"""
Waveform averaging for noise reduction.

Rolling N-frame averager that maintains a circular buffer per channel
and returns the element-wise mean.
"""

import collections

import numpy as np


class WaveformAverager:
    """Rolling waveform averager.

    Usage:
        avg = WaveformAverager(count=16)
        averaged = avg.add(channel=1, voltage=raw_voltage)
    """

    def __init__(self, count: int = 0):
        self._count = count
        self._buffers: dict[int, collections.deque] = {}

    @property
    def count(self) -> int:
        return self._count

    def set_count(self, count: int):
        """Change averaging depth. Clears all buffers."""
        self._count = count
        self._buffers.clear()

    def add(self, channel: int, voltage: np.ndarray) -> np.ndarray:
        """Add a waveform frame and return the current average.

        Returns the input unchanged if count <= 1.
        """
        if self._count <= 1:
            return voltage

        buf = self._buffers.get(channel)
        if buf is None:
            buf = collections.deque(maxlen=self._count)
            self._buffers[channel] = buf

        # Reset buffer if array length changed (safety)
        if buf and len(buf[0]) != len(voltage):
            buf.clear()

        buf.append(voltage.copy())
        return np.mean(np.stack(buf), axis=0)

    def reset(self, channel: int | None = None):
        """Clear buffer for one or all channels."""
        if channel is None:
            self._buffers.clear()
        else:
            self._buffers.pop(channel, None)
