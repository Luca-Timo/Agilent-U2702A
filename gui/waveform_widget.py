"""
Waveform display widget using PyQtGraph.

Dark background, custom graticule, N-channel support with configurable colors.
Per-channel GND markers on Y-axis, trigger position marker on X-axis.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from gui.theme import (
    BG_PLOT, GRID_COLOR, TEXT_DIM, ACCENT_BLUE,
    NUM_CHANNELS, channel_color,
)
from processing.waveform import WaveformData


class WaveformWidget(pg.PlotWidget):
    """Real-time waveform display with graticule overlay.

    Supports N channels with dynamic trace creation/removal.
    Includes per-channel GND markers and trigger position indicator.
    """

    NUM_H_DIVS = 10   # Horizontal divisions
    NUM_V_DIVS = 8    # Vertical divisions

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__(parent=parent, background=BG_PLOT)

        self._num_channels = num_channels
        self._traces: dict[int, pg.PlotDataItem] = {}
        self._colors: dict[int, str] = {}

        # Per-channel GND marker state (single TextItem badge per channel)
        self._gnd_markers: dict[int, pg.TextItem] = {}
        self._channel_offsets: dict[int, float] = {}

        # Trigger position marker
        self._trigger_marker: pg.ScatterPlotItem | None = None
        self._trigger_pos: float = 0.0  # Time position (seconds)

        # Default colors
        for ch in range(1, num_channels + 1):
            self._colors[ch] = channel_color(ch)
            self._channel_offsets[ch] = 0.0

        # Configure plot
        self._setup_plot()
        self._draw_graticule()
        self._create_trigger_marker()

        # Initial axis range
        self._v_per_div = 1.0
        self._t_per_div = 1e-3
        self._update_axis_range()

    def _setup_plot(self):
        """Configure the plot appearance."""
        plot = self.getPlotItem()

        # Hide default axes
        plot.hideAxis('bottom')
        plot.hideAxis('left')

        # Disable mouse interaction (knobs control scaling)
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)
        self.setMouseTracking(False)

        # CRITICAL: Disable auto-range — we set axis range manually
        # via knobs. Without this, PyQtGraph auto-ranges on each data
        # update, which overrides our T/div and V/div scaling.
        vb = plot.getViewBox()
        vb.enableAutoRange(axis='xy', enable=False)
        vb.setDefaultPadding(0)

        # Remove default grid
        plot.showGrid(x=False, y=False)

    def _draw_graticule(self):
        """Draw oscilloscope-style grid lines."""
        self._graticule_lines = []

        pen_major = pg.mkPen(color=GRID_COLOR, width=0.5, style=Qt.PenStyle.DashLine)
        pen_center = pg.mkPen(color="#444444", width=0.8, style=Qt.PenStyle.SolidLine)

        # Vertical center line
        line = pg.InfiniteLine(pos=0, angle=90, pen=pen_center)
        self.addItem(line)
        self._graticule_lines.append(('vcenter', line))

        # Horizontal center line
        line = pg.InfiniteLine(pos=0, angle=0, pen=pen_center)
        self.addItem(line)
        self._graticule_lines.append(('hcenter', line))

        # Vertical grid lines (excluding center)
        for i in range(-self.NUM_H_DIVS // 2, self.NUM_H_DIVS // 2 + 1):
            if i == 0:
                continue
            line = pg.InfiniteLine(pos=0, angle=90, pen=pen_major)
            self.addItem(line)
            self._graticule_lines.append(('vgrid', line, i))

        # Horizontal grid lines (excluding center)
        for i in range(-self.NUM_V_DIVS // 2, self.NUM_V_DIVS // 2 + 1):
            if i == 0:
                continue
            line = pg.InfiniteLine(pos=0, angle=0, pen=pen_major)
            self.addItem(line)
            self._graticule_lines.append(('hgrid', line, i))

    def _create_trigger_marker(self):
        """Create the trigger position marker (▼ at top of plot)."""
        self._trigger_marker = pg.ScatterPlotItem(
            pos=np.array([[0.0, 0.0]]),
            symbol='t',            # Downward-pointing triangle
            size=12,
            pen=pg.mkPen(ACCENT_BLUE, width=1),
            brush=pg.mkBrush(ACCENT_BLUE),
        )
        self.addItem(self._trigger_marker)

    def _update_axis_range(self):
        """Update axis range based on current V/div and T/div."""
        h_half = (self.NUM_H_DIVS / 2) * self._t_per_div
        v_half = (self.NUM_V_DIVS / 2) * self._v_per_div

        self.setXRange(-h_half, h_half, padding=0)
        self.setYRange(-v_half, v_half, padding=0)

        # Reposition graticule lines
        for item in self._graticule_lines:
            tag = item[0]
            line = item[1]
            if tag == 'vgrid':
                div_idx = item[2]
                line.setPos(div_idx * self._t_per_div)
            elif tag == 'hgrid':
                div_idx = item[2]
                line.setPos(div_idx * self._v_per_div)

        # Reposition GND markers to left edge
        self._update_gnd_positions()

        # Reposition trigger marker to top edge
        self._update_trigger_position()

    def _update_gnd_positions(self):
        """Reposition all GND markers to the left edge of the plot."""
        left_x = -(self.NUM_H_DIVS / 2) * self._t_per_div

        for ch, marker in self._gnd_markers.items():
            offset = self._channel_offsets.get(ch, 0.0)
            marker.setPos(left_x, offset)

    def _update_trigger_position(self):
        """Reposition the trigger marker to the top edge of the plot."""
        if self._trigger_marker is not None:
            top_y = (self.NUM_V_DIVS / 2) * self._v_per_div
            self._trigger_marker.setData(
                pos=np.array([[self._trigger_pos, top_y]])
            )

    # --- Public API ---

    def set_scales(self, v_per_div: float, t_per_div: float):
        """Update axis scaling."""
        self._v_per_div = v_per_div
        self._t_per_div = t_per_div
        self._update_axis_range()

    def set_channel_color(self, channel: int, color: str):
        """Set waveform color for a channel."""
        self._colors[channel] = color
        if channel in self._traces:
            self._traces[channel].setPen(pg.mkPen(color=color, width=1.5))
        # Recreate GND marker with new color
        if channel in self._gnd_markers:
            self._remove_gnd_marker(channel)
            self._create_gnd_marker(channel)

    def set_channel_enabled(self, channel: int, enabled: bool):
        """Show or hide a channel trace and its GND marker."""
        if enabled and channel not in self._traces:
            # Create trace
            color = self._colors.get(channel, channel_color(channel))
            trace = self.plot([], [], pen=pg.mkPen(color=color, width=1.5))
            self._traces[channel] = trace
            # Create GND marker
            self._create_gnd_marker(channel)
        elif not enabled and channel in self._traces:
            # Remove trace
            self.removeItem(self._traces[channel])
            del self._traces[channel]
            # Remove GND marker
            self._remove_gnd_marker(channel)

    def set_channel_offset(self, channel: int, offset: float):
        """Update a channel's offset — moves its GND marker on the Y-axis."""
        self._channel_offsets[channel] = offset
        self._update_gnd_positions()

    def set_trigger_position(self, time_pos: float):
        """Update the trigger position marker on the X-axis."""
        self._trigger_pos = time_pos
        self._update_trigger_position()

    def update_waveform(self, waveform: WaveformData):
        """Update a channel's waveform display.

        Args:
            waveform: Processed waveform data with voltage and time arrays.
        """
        ch = waveform.channel

        # Auto-create trace if not exists
        if ch not in self._traces:
            color = self._colors.get(ch, channel_color(ch))
            trace = self.plot([], [], pen=pg.mkPen(color=color, width=1.5))
            self._traces[ch] = trace
            self._create_gnd_marker(ch)

        self._traces[ch].setData(waveform.time_axis, waveform.voltage)

    def clear_channel(self, channel: int):
        """Clear waveform data for a channel."""
        if channel in self._traces:
            self._traces[channel].setData([], [])

    def clear_all(self):
        """Clear all waveform data."""
        for trace in self._traces.values():
            trace.setData([], [])

    # --- GND marker helpers ---

    def _create_gnd_marker(self, channel: int):
        """Create a GND badge on the left edge for a channel.

        Renders as a bordered, colored label: ▶ CH1  (or just ▶ 1)
        Positioned at the left plot edge, at the channel's 0V offset.
        """
        if channel in self._gnd_markers:
            return  # Already exists

        color = self._colors.get(channel, channel_color(channel))
        left_x = -(self.NUM_H_DIVS / 2) * self._t_per_div
        offset = self._channel_offsets.get(channel, 0.0)

        # HTML badge: bordered box with channel number + arrow
        html = (
            f'<div style="'
            f'background-color: {color};'
            f'color: #000000;'
            f'border: 1px solid {color};'
            f'border-radius: 2px;'
            f'padding: 1px 4px;'
            f'font-size: 11px;'
            f'font-weight: bold;'
            f'font-family: Menlo, monospace;'
            f'">{channel} ▶</div>'
        )

        marker = pg.TextItem(html=html, anchor=(0.0, 0.5))
        marker.setPos(left_x, offset)
        self.addItem(marker)
        self._gnd_markers[channel] = marker

    def _remove_gnd_marker(self, channel: int):
        """Remove a channel's GND marker."""
        if channel in self._gnd_markers:
            self.removeItem(self._gnd_markers[channel])
            del self._gnd_markers[channel]
