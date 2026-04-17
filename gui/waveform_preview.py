"""
Small PyQtGraph waveform preview — renders the *programmed* waveform
analytically from the driver's setpoints.

This is not an oscilloscope capture; there's no hardware round-trip.
We know the shape, frequency, amplitude, offset, and phase, so we
build one period of the ideal waveform in numpy and plot it. Updates
instantly on any knob change.

The same widget is reusable for any instrument that produces a
parametric waveform (function generators today; power supply
ripple/modulation previews later).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen

from gui.theme import (
    BG_PLOT, GRID_COLOR, TEXT_DIM, ACCENT_BLUE,
    format_frequency, format_voltage,
)


# Samples per period — enough to render any shape smoothly without
# being wasteful. 500 gives a visibly smooth sine in a 600-pixel-wide
# preview area.
_PERIODS_SHOWN = 2
_SAMPLES_PER_PERIOD = 500


class WaveformPreview(pg.PlotWidget):
    """Preview plot for an ideal parametric waveform.

    Call ``set_waveform(shape, freq, amp, offset, phase)`` any time
    the setpoints change; the plot redraws in place.
    """

    WAVEFORMS = ("SIN", "SQU", "TRI", "RAMP", "NOIS", "DC")

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setBackground(BG_PLOT)
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self.hideButtons()

        # Keep axis labels but drop the interactive bits — this is a
        # status display, not a zoomable plot.
        self.getAxis("bottom").setPen(pg.mkPen(GRID_COLOR))
        self.getAxis("left").setPen(pg.mkPen(GRID_COLOR))
        self.getAxis("bottom").setTextPen(pg.mkPen(TEXT_DIM))
        self.getAxis("left").setTextPen(pg.mkPen(TEXT_DIM))
        self.setLabel("bottom", "t")
        self.setLabel("left", "V")
        self.showGrid(x=True, y=True, alpha=0.2)

        # Single trace; replaced in place on updates.
        self._trace = self.plot(
            pen=QPen(pg.mkColor(ACCENT_BLUE), 2),
            antialias=True,
        )

        # Header text item (waveform label + freq + amp readout).
        self._header = pg.TextItem(
            text="", anchor=(0, 0),
            color=pg.mkColor(TEXT_DIM),
        )
        self._header.setPos(0, 0)
        self.addItem(self._header, ignoreBounds=True)

        # Initial render — blank sine at 0 V so the widget doesn't
        # show an empty plot on first paint.
        self.set_waveform("SIN", 1000.0, 1.0, 0.0, 0.0)

    # -- Public API ---------------------------------------------------

    def set_waveform(self, shape: str, frequency: float,
                     amplitude: float, offset: float = 0.0,
                     phase: float = 0.0) -> None:
        """Redraw with the given parametric setpoints.

        Args:
            shape: one of SIN / SQU / TRI / RAMP / NOIS / DC (case-insensitive).
            frequency: Hz. Ignored for DC.
            amplitude: peak-to-peak V. DC uses this as the flat level.
            offset: DC offset V added to every sample.
            phase: degrees; 0–360, wraps.
        """
        shape = shape.upper()
        if shape not in self.WAVEFORMS:
            shape = "SIN"

        # Build one period's worth of time (for DC we still need a
        # flat line, so any positive frequency works).
        freq = max(1e-9, frequency)
        period = 1.0 / freq
        n = _SAMPLES_PER_PERIOD * _PERIODS_SHOWN
        t = np.linspace(0.0, _PERIODS_SHOWN * period, n, endpoint=False)

        y = self._synthesize(shape, freq, amplitude, offset, phase, t)

        self._trace.setData(t, y)

        # Fix the Y range so the view doesn't autoscale jitter on a
        # knob turn; pad by 20% of Vpp.
        pad = 0.2 * max(amplitude, 0.01)
        self.setYRange(offset - amplitude / 2 - pad,
                       offset + amplitude / 2 + pad,
                       padding=0)
        self.setXRange(0.0, _PERIODS_SHOWN * period, padding=0)

        self._header.setText(
            f"{shape}   {format_frequency(frequency)}   "
            f"{format_voltage(amplitude)} pp   "
            f"offset {format_voltage(offset)}"
        )
        # Anchor header to the top-left data coords.
        self._header.setPos(0.0, offset + amplitude / 2 + pad)

    # -- Analytical synthesis ----------------------------------------

    @staticmethod
    def _synthesize(shape: str, freq: float, amp: float, offset: float,
                    phase_deg: float, t: np.ndarray) -> np.ndarray:
        phase_rad = np.deg2rad(phase_deg)
        omega = 2 * np.pi * freq
        half_amp = amp / 2.0

        if shape == "SIN":
            return offset + half_amp * np.sin(omega * t + phase_rad)

        if shape == "SQU":
            return offset + half_amp * np.sign(
                np.sin(omega * t + phase_rad) + 1e-12,
            )

        if shape == "TRI":
            # Triangle: integrate square; scale so range = ±half_amp.
            phase_t = (t * freq + phase_deg / 360.0) % 1.0
            tri = 1.0 - 4.0 * np.abs(phase_t - 0.5)
            return offset + half_amp * tri

        if shape == "RAMP":
            # Sawtooth: -half_amp → +half_amp over one period.
            phase_t = (t * freq + phase_deg / 360.0) % 1.0
            return offset + half_amp * (2.0 * phase_t - 1.0)

        if shape == "NOIS":
            # Deterministic noise — same seed every redraw so the
            # visual is stable while the user adjusts other knobs.
            rng = np.random.default_rng(seed=42)
            noise = rng.uniform(-1.0, 1.0, size=t.shape)
            return offset + half_amp * noise

        if shape == "DC":
            return np.full_like(t, offset + half_amp)

        # Fallback — silence, but don't crash.
        return np.full_like(t, offset)
