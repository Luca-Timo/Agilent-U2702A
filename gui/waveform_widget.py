"""
Waveform display widget using PyQtGraph.

Dark background, custom graticule, N-channel support with configurable colors.
Per-channel GND markers on Y-axis, trigger level + position indicators.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QRect, QPoint
from PySide6.QtGui import QColor, QFont, QPen, QBrush, QPainter
from PySide6.QtWidgets import QRubberBand

from gui.theme import (
    BG_PLOT, GRID_COLOR, TEXT_DIM, ACCENT_BLUE,
    NUM_CHANNELS, channel_color,
)
from processing.waveform import WaveformData

# Trigger marker color
TRIGGER_COLOR = "#FF4444"

# Cursor colors
CURSOR_COLOR = "#FF8800"  # Orange — distinct from red trigger and gray grid


class WaveformWidget(pg.PlotWidget):
    """Real-time waveform display with graticule overlay.

    Supports N channels with dynamic trace creation/removal.
    Includes per-channel GND markers, trigger level line, and trigger
    position indicator.
    """

    NUM_H_DIVS = 10   # Horizontal divisions
    NUM_V_DIVS = 8    # Vertical divisions

    # Emitted when user finishes a drag-to-zoom rectangle
    # Args: t_min, v_min, t_max, v_max (data coordinates)
    zoom_requested = Signal(float, float, float, float)

    # Emitted continuously while user drags markers on the graph
    trigger_level_dragged = Signal(float)   # new trigger level (voltage)
    trigger_pos_dragged = Signal(float)     # new h_position (seconds)
    offset_dragged = Signal(int, float)     # channel, new offset (voltage)

    # Emitted when user drags a measurement cursor
    # Args: cursor_type ("time"/"voltage"), cursor_id (1 or 2), new_value
    cursor_moved = Signal(str, int, float)

    MIN_DRAG_PX = 10  # Minimum pixel drag to trigger zoom
    _HIT_THRESHOLD_PX = 8  # Pixel proximity for marker hit detection

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__(parent=parent, background=BG_PLOT)

        self._num_channels = num_channels
        self._traces: dict[int, pg.PlotDataItem] = {}
        self._colors: dict[int, str] = {}

        # Per-channel GND marker state (single TextItem badge per channel)
        self._gnd_markers: dict[int, pg.TextItem] = {}
        self._channel_offsets: dict[int, float] = {}
        self._enabled_channels: set[int] = set()
        self._probe_factors: dict[int, float] = {}

        # Per-channel effective V/div (raw × probe) for independent scaling.
        # Each channel's waveform is scaled by display_vdiv / ch_vdiv
        # so channels with different V/div settings appear at correct sizes.
        self._ch_effective_vdivs: dict[int, float] = {}

        # Cached raw (unscaled) waveform data per channel for instant
        # replotting when scale factors change (avoids visual glitch
        # between axis change and next acquisition update).
        self._raw_waveforms: dict[int, tuple] = {}  # ch → (time, voltage)

        # Horizontal position (view offset from position knob)
        self._h_position: float = 0.0

        # Trigger state
        self._trigger_pos: float = 0.0      # Time position (seconds)
        self._trigger_level: float = 0.0    # Voltage level
        self._trigger_slope: str = "POS"    # Trigger slope (POS/NEG/EITH/ALT)
        self._trigger_source_ch: int = 1    # Which channel is the trigger source
        self._trigger_source_offset: float = 0.0  # Source channel's Y offset
        self._trigger_pos_marker: pg.ScatterPlotItem | None = None
        self._trigger_level_line: pg.InfiniteLine | None = None
        self._trigger_level_badge: pg.TextItem | None = None

        # Trigger crossing marker (on the waveform trace itself)
        self._trigger_crossing_dot: pg.ScatterPlotItem | None = None
        self._trigger_crossing_label: pg.TextItem | None = None
        self._trigger_crossing_ch: int | None = None  # Which channel owns the marker

        # Cursor state
        self._cursor_mode: str = "off"  # "off", "time", "voltage", "both"
        self._time_cursors: list[float] = [0.0, 0.0]   # [t1, t2] in seconds
        self._volt_cursors: list[float] = [0.0, 0.0]   # [v1, v2] in volts
        self._time_cursor_lines: list[pg.InfiniteLine | None] = [None, None]
        self._volt_cursor_lines: list[pg.InfiniteLine | None] = [None, None]
        self._time_cursor_badges: list[pg.TextItem | None] = [None, None]
        self._volt_cursor_badges: list[pg.TextItem | None] = [None, None]

        # Measurement hover highlight lines (temporary, shown on hover)
        self._highlight_lines: list[pg.InfiniteLine] = []

        # Drag state: None, 'trigger_level', 'trigger_pos', ('offset', ch),
        #             ('cursor_time', 0/1), ('cursor_volt', 0/1)
        self._dragging: str | tuple | None = None
        self._drag_prev_px: QPoint | None = None  # for pixel-delta approach

        # Drag-to-zoom state (uses QRubberBand — a plain widget overlay,
        # completely outside the PyQtGraph scene to avoid any artifacts)
        self._zoom_origin: QPoint | None = None
        self._rubber_band: QRubberBand | None = None

        # Default colors
        for ch in range(1, num_channels + 1):
            self._colors[ch] = channel_color(ch)
            self._channel_offsets[ch] = 0.0

        # Configure plot
        self._setup_plot()
        self._draw_graticule()
        self._create_trigger_indicators()
        self._create_cursor_items()

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

        # Disable all mouse interaction — knobs and drag-to-zoom handle it
        plot.setMouseEnabled(x=False, y=False)
        plot.setMenuEnabled(False)
        self.setDragMode(self.DragMode.NoDrag)
        # Fully disable ViewBox mouse interaction — we handle everything
        # ourselves via drag-to-zoom.  PyQtGraph has its own event system
        # (mouseDragEvent / mouseClickEvent) on top of Qt's, so we must
        # disable at multiple layers to prevent its rubber-band overlay.
        vb = plot.getViewBox()
        vb.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        vb.mouseDragEvent = lambda ev, axis=None: None
        vb.mouseClickEvent = lambda ev: None
        # Remove the built-in rubber-band scale box completely
        if vb.rbScaleBox is not None:
            vb.removeItem(vb.rbScaleBox)
            vb.rbScaleBox = None
        self.setMouseTracking(False)

        # CRITICAL: Disable auto-range — we set axis range manually
        # via knobs. Without this, PyQtGraph auto-ranges on each data
        # update, which overrides our T/div and V/div scaling.
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

    def _create_trigger_indicators(self):
        """Create trigger position marker (▼ top) and trigger level line + badge."""
        # --- Trigger position marker (▼ at top of plot) ---
        self._trigger_pos_marker = pg.ScatterPlotItem(
            pos=np.array([[0.0, 0.0]]),
            symbol='t',            # Downward-pointing triangle
            size=12,
            pen=pg.mkPen(TRIGGER_COLOR, width=1),
            brush=pg.mkBrush(TRIGGER_COLOR),
        )
        self.addItem(self._trigger_pos_marker)

        # --- Trigger level horizontal line (dashed, subtle) ---
        self._trigger_level_line = pg.InfiniteLine(
            pos=0.0, angle=0,
            pen=pg.mkPen(TRIGGER_COLOR, width=0.8, style=Qt.PenStyle.DashLine),
        )
        self.addItem(self._trigger_level_line)

        # --- Trigger level badge on right edge (T ◀ level) ---
        self._trigger_level_badge = pg.TextItem(
            html=self._trigger_badge_html(self._trigger_level),
            anchor=(1.0, 0.5),  # Right-aligned
        )
        self.addItem(self._trigger_level_badge)

        # --- Trigger crossing marker (on the waveform trace) ---
        # Bright dot at the exact crossing point
        self._trigger_crossing_dot = pg.ScatterPlotItem(
            pos=np.array([[0.0, 0.0]]),
            symbol='o',
            size=10,
            pen=pg.mkPen('#ffffff', width=2),
            brush=pg.mkBrush(TRIGGER_COLOR),
        )
        self._trigger_crossing_dot.setVisible(False)
        self.addItem(self._trigger_crossing_dot)

        # Slope arrow label next to the crossing point
        self._trigger_crossing_label = pg.TextItem(
            html=self._crossing_label_html(self._trigger_slope),
            anchor=(0.0, 1.0),  # Left-aligned, bottom-anchored (sits above+right)
        )
        self._trigger_crossing_label.setVisible(False)
        self.addItem(self._trigger_crossing_label)

    @staticmethod
    def _trigger_badge_html(level: float) -> str:
        """Generate HTML for the trigger level badge."""
        from gui.theme import format_voltage
        text = format_voltage(level)
        return (
            f'<div style="'
            f'background-color: {TRIGGER_COLOR};'
            f'color: #ffffff;'
            f'border: 1px solid {TRIGGER_COLOR};'
            f'border-radius: 2px;'
            f'padding: 1px 4px;'
            f'font-size: 10px;'
            f'font-weight: bold;'
            f'font-family: Menlo, monospace;'
            f'">T ◀ {text}</div>'
        )

    @staticmethod
    def _crossing_label_html(slope: str) -> str:
        """Generate HTML for the trigger crossing label on the waveform."""
        icons = {
            "POS": "↗",
            "NEG": "↘",
            "EITH": "↕",
            "ALT": "⇅",
        }
        icon = icons.get(slope, "↗")
        return (
            f'<div style="'
            f'background-color: rgba(255,68,68,0.85);'
            f'color: #ffffff;'
            f'border: 2px solid #ffffff;'
            f'border-radius: 3px;'
            f'padding: 0px 4px;'
            f'font-size: 16px;'
            f'font-weight: bold;'
            f'font-family: Menlo, monospace;'
            f'text-align: center;'
            f'">{icon}</div>'
        )

    def _ch_scale(self, ch: int) -> float:
        """Scale factor for probe-tip voltage → display coordinates.

        Used by measurement highlights where voltage values are already
        in probe-tip space (i.e., already multiplied by probe_factor).

        Each channel has its own effective V/div. The display axis uses
        the active channel's V/div (``self._v_per_div``). A channel with
        a larger V/div appears compressed, a smaller one appears stretched.

        Returns 1.0 when the channel's V/div matches the display.
        """
        ch_vdiv = self._ch_effective_vdivs.get(ch, self._v_per_div)
        if ch_vdiv <= 0:
            return 1.0
        return self._v_per_div / ch_vdiv

    def _voltage_scale(self, ch: int) -> float:
        """Scale factor for scope-space voltage → display coordinates.

        Combines inter-channel V/div normalization with probe attenuation.
        Scope-space voltage (what the ADC measures at the BNC input) is
        multiplied by this factor to get the display coordinate.

        Equivalent to ``_ch_scale(ch) * probe_factor(ch)``.
        """
        return self._ch_scale(ch) * self._probe_factors.get(ch, 1.0)

    def _replot_traces(self, channels: list[int] | None = None):
        """Re-apply per-channel scaling to cached trace data.

        Called when scale factors change (display V/div or a channel's
        V/div) so existing on-screen traces update immediately without
        waiting for the next acquisition frame.
        """
        chs = channels if channels is not None else list(self._raw_waveforms.keys())
        for ch in chs:
            if ch in self._raw_waveforms and ch in self._traces:
                time_axis, voltage = self._raw_waveforms[ch]
                scale = self._voltage_scale(ch)
                if scale != 1.0:
                    self._traces[ch].setData(time_axis, voltage * scale)
                else:
                    self._traces[ch].setData(time_axis, voltage)

    def _update_axis_range(self):
        """Update axis range based on current V/div, T/div, and position."""
        h_half = (self.NUM_H_DIVS / 2) * self._t_per_div
        v_half = (self.NUM_V_DIVS / 2) * self._v_per_div

        # Offset X range by horizontal position
        self.setXRange(self._h_position - h_half,
                       self._h_position + h_half, padding=0)
        self.setYRange(-v_half, v_half, padding=0)

        # Reposition graticule lines (centered on view, not on origin)
        for item in self._graticule_lines:
            tag = item[0]
            line = item[1]
            if tag == 'vcenter':
                line.setPos(self._h_position)
            elif tag == 'vgrid':
                div_idx = item[2]
                line.setPos(self._h_position + div_idx * self._t_per_div)
            elif tag == 'hgrid':
                div_idx = item[2]
                line.setPos(div_idx * self._v_per_div)

        # Reposition GND markers to left edge
        self._update_gnd_positions()

        # Reposition trigger indicators
        self._update_trigger_position()
        self._update_trigger_level_position()

        # Reposition cursor badges at new edges
        self._update_cursor_positions()

    def _update_gnd_positions(self):
        """Reposition all GND markers to the left edge of the plot."""
        left_x = self._h_position - (self.NUM_H_DIVS / 2) * self._t_per_div

        for ch, marker in self._gnd_markers.items():
            offset = self._channel_offsets.get(ch, 0.0)
            # Scale offset by per-channel factor (including probe) so
            # GND marker aligns with the channel's waveform in display space.
            marker.setPos(left_x, offset * self._voltage_scale(ch))

    def _update_trigger_position(self):
        """Reposition the trigger position marker to the top edge."""
        if self._trigger_pos_marker is not None:
            top_y = (self.NUM_V_DIVS / 2) * self._v_per_div
            self._trigger_pos_marker.setData(
                pos=np.array([[self._trigger_pos, top_y]])
            )

    def _update_trigger_level_position(self):
        """Reposition the trigger level line and right-edge badge.

        The trigger level is offset by the source channel's vertical offset
        so the line aligns with the waveform on screen.  Both the level
        and offset are scaled by the trigger source channel's display
        scale factor for per-channel V/div independence.
        """
        scale = self._voltage_scale(self._trigger_source_ch)
        screen_y = (self._trigger_level + self._trigger_source_offset) * scale

        if self._trigger_level_line is not None:
            self._trigger_level_line.setPos(screen_y)

        if self._trigger_level_badge is not None:
            right_x = self._h_position + (self.NUM_H_DIVS / 2) * self._t_per_div
            self._trigger_level_badge.setPos(right_x, screen_y)

    # --- Cursor items ---

    def _create_cursor_items(self):
        """Create measurement cursor lines and edge badges (initially hidden)."""
        from gui.theme import format_voltage, format_time

        styles = [
            pg.mkPen(CURSOR_COLOR, width=1.2, style=Qt.PenStyle.SolidLine),
            pg.mkPen(CURSOR_COLOR, width=1.2, style=Qt.PenStyle.DashDotLine),
        ]

        for i in range(2):
            # Time cursors (vertical lines)
            line = pg.InfiniteLine(pos=0.0, angle=90, pen=styles[i])
            line.setVisible(False)
            self.addItem(line)
            self._time_cursor_lines[i] = line

            badge = pg.TextItem(
                html=self._cursor_badge_html(f"C{i+1}", "0 s"),
                anchor=(0.5, 1.0),  # Center-top
            )
            badge.setVisible(False)
            self.addItem(badge)
            self._time_cursor_badges[i] = badge

            # Voltage cursors (horizontal lines)
            line = pg.InfiniteLine(pos=0.0, angle=0, pen=styles[i])
            line.setVisible(False)
            self.addItem(line)
            self._volt_cursor_lines[i] = line

            badge = pg.TextItem(
                html=self._cursor_badge_html(f"C{i+1}", "0 V"),
                anchor=(1.0, 0.5),  # Right-aligned
            )
            badge.setVisible(False)
            self.addItem(badge)
            self._volt_cursor_badges[i] = badge

    @staticmethod
    def _cursor_badge_html(label: str, value: str) -> str:
        """Generate HTML for a cursor edge badge."""
        return (
            f'<div style="'
            f'background-color: {CURSOR_COLOR};'
            f'color: #000000;'
            f'border: 1px solid {CURSOR_COLOR};'
            f'border-radius: 2px;'
            f'padding: 1px 4px;'
            f'font-size: 9px;'
            f'font-weight: bold;'
            f'font-family: Menlo, monospace;'
            f'">{label} {value}</div>'
        )

    def _update_cursor_positions(self):
        """Reposition cursor badges at plot edges after axis changes."""
        from gui.theme import format_time, format_voltage

        top_y = (self.NUM_V_DIVS / 2) * self._v_per_div
        right_x = self._h_position + (self.NUM_H_DIVS / 2) * self._t_per_div

        for i in range(2):
            # Time cursor badge at top edge
            if self._time_cursor_badges[i] is not None:
                self._time_cursor_badges[i].setPos(self._time_cursors[i], top_y)
                if self._time_cursor_badges[i].isVisible():
                    self._time_cursor_badges[i].setHtml(
                        self._cursor_badge_html(
                            f"C{i+1}", format_time(self._time_cursors[i])
                        )
                    )

            # Voltage cursor badge at right edge
            if self._volt_cursor_badges[i] is not None:
                self._volt_cursor_badges[i].setPos(right_x, self._volt_cursors[i])
                if self._volt_cursor_badges[i].isVisible():
                    self._volt_cursor_badges[i].setHtml(
                        self._cursor_badge_html(
                            f"C{i+1}", format_voltage(self._volt_cursors[i])
                        )
                    )

    # --- Public API ---

    def set_scales(self, v_per_div: float, t_per_div: float):
        """Update axis scaling."""
        self._v_per_div = v_per_div
        self._t_per_div = t_per_div
        self._update_axis_range()
        # Re-scale all traces immediately so other channels don't
        # visually jump while waiting for the next acquisition frame.
        self._replot_traces()

    def set_h_position(self, position: float):
        """Shift the horizontal view position.

        Moves the view window so the waveform scrolls left/right.
        The trigger marker (▼) stays at t=0 in data coordinates.
        """
        self._h_position = position
        self._update_axis_range()

    def set_channel_vdiv(self, channel: int, effective_vdiv: float):
        """Set a channel's effective V/div for independent per-channel scaling.

        Args:
            channel: Channel number (1-based).
            effective_vdiv: Effective V/div (raw scope V/div × probe factor).
        """
        self._ch_effective_vdivs[channel] = effective_vdiv
        # Reposition GND markers and trigger level with new scale factors
        self._update_gnd_positions()
        self._update_trigger_level_position()
        # Immediately replot this channel's trace with the new scale
        self._replot_traces([channel])

    def set_trigger_source_channel(self, channel: int):
        """Set which channel is the trigger source (for per-channel scaling).

        The trigger level line position is scaled by this channel's
        V/div factor so it aligns with the source waveform.
        """
        self._trigger_source_ch = channel
        self._update_trigger_level_position()

    def set_channel_color(self, channel: int, color: str):
        """Set waveform color for a channel."""
        self._colors[channel] = color
        if channel in self._traces:
            self._traces[channel].setPen(pg.mkPen(color=color, width=1.5))
        # Recreate GND marker with new color
        if channel in self._gnd_markers:
            self._remove_gnd_marker(channel)
            self._create_gnd_marker(channel)

    def set_channel_probe(self, channel: int, factor: float):
        """Update probe factor — refreshes GND marker badge."""
        self._probe_factors[channel] = factor
        if channel in self._gnd_markers:
            self._remove_gnd_marker(channel)
            self._create_gnd_marker(channel)

    def set_channel_enabled(self, channel: int, enabled: bool):
        """Show or hide a channel trace and its GND marker."""
        if enabled:
            self._enabled_channels.add(channel)
            if channel not in self._traces:
                # Create trace
                color = self._colors.get(channel, channel_color(channel))
                trace = self.plot([], [], pen=pg.mkPen(color=color, width=1.5))
                self._traces[channel] = trace
                # Create GND marker
                self._create_gnd_marker(channel)
        else:
            self._enabled_channels.discard(channel)
            if channel in self._traces:
                # Remove trace
                self.removeItem(self._traces[channel])
                del self._traces[channel]
                # Remove cached raw data
                self._raw_waveforms.pop(channel, None)
                # Remove GND marker
                self._remove_gnd_marker(channel)
            # Hide trigger crossing marker if it belongs to this channel
            if self._trigger_crossing_ch == channel:
                self._trigger_crossing_ch = None
                if self._trigger_crossing_dot is not None:
                    self._trigger_crossing_dot.setVisible(False)
                if self._trigger_crossing_label is not None:
                    self._trigger_crossing_label.setVisible(False)

    def set_channel_offset(self, channel: int, offset: float):
        """Update a channel's offset — moves its GND marker on the Y-axis."""
        self._channel_offsets[channel] = offset
        self._update_gnd_positions()

    def set_trigger_position(self, time_pos: float):
        """Update the trigger position marker on the X-axis (▼ at top)."""
        self._trigger_pos = time_pos
        self._update_trigger_position()

    def set_trigger_level(self, level: float):
        """Update the trigger level line and right-edge badge."""
        self._trigger_level = level

        # Update badge text and reposition (line + badge use source offset)
        if self._trigger_level_badge is not None:
            self._trigger_level_badge.setHtml(
                self._trigger_badge_html(level)
            )
        self._update_trigger_level_position()

    def set_trigger_slope(self, slope: str):
        """Update the trigger slope (used by crossing label on the trace).

        Args:
            slope: One of "POS", "NEG", "EITH", "ALT"
        """
        self._trigger_slope = slope

    def set_trigger_source_offset(self, offset: float):
        """Set the trigger source channel's vertical offset.

        The trigger level line shifts by this offset so it aligns with
        the source channel's waveform on screen.
        """
        self._trigger_source_offset = offset
        self._update_trigger_level_position()

    def set_cursor_mode(self, mode: str):
        """Set cursor mode: "off", "time", "voltage", or "both".

        When switching to a new mode, cursors are positioned at ±25%
        of the visible range for a useful starting point.
        """
        old_mode = self._cursor_mode
        self._cursor_mode = mode

        show_time = mode in ("time", "both")
        show_volt = mode in ("voltage", "both")

        # Set initial positions when first turning on a cursor type
        if show_time and old_mode not in ("time", "both"):
            h_half = (self.NUM_H_DIVS / 2) * self._t_per_div
            self._time_cursors[0] = self._h_position - 0.25 * h_half
            self._time_cursors[1] = self._h_position + 0.25 * h_half

        if show_volt and old_mode not in ("voltage", "both"):
            v_half = (self.NUM_V_DIVS / 2) * self._v_per_div
            self._volt_cursors[0] = 0.25 * v_half
            self._volt_cursors[1] = -0.25 * v_half

        for i in range(2):
            if self._time_cursor_lines[i] is not None:
                self._time_cursor_lines[i].setVisible(show_time)
                self._time_cursor_lines[i].setPos(self._time_cursors[i])
            if self._time_cursor_badges[i] is not None:
                self._time_cursor_badges[i].setVisible(show_time)

            if self._volt_cursor_lines[i] is not None:
                self._volt_cursor_lines[i].setVisible(show_volt)
                self._volt_cursor_lines[i].setPos(self._volt_cursors[i])
            if self._volt_cursor_badges[i] is not None:
                self._volt_cursor_badges[i].setVisible(show_volt)

        self._update_cursor_positions()

    def set_time_cursor(self, cursor_id: int, value: float):
        """Move a time cursor to a new position.

        Args:
            cursor_id: 0 or 1 (C1 or C2).
            value: Time position in seconds.
        """
        self._time_cursors[cursor_id] = value
        if self._time_cursor_lines[cursor_id] is not None:
            self._time_cursor_lines[cursor_id].setPos(value)
        self._update_cursor_positions()
        self.cursor_moved.emit("time", cursor_id + 1, value)

    def set_volt_cursor(self, cursor_id: int, value: float):
        """Move a voltage cursor to a new position.

        Args:
            cursor_id: 0 or 1 (C1 or C2).
            value: Voltage position.
        """
        self._volt_cursors[cursor_id] = value
        if self._volt_cursor_lines[cursor_id] is not None:
            self._volt_cursor_lines[cursor_id].setPos(value)
        self._update_cursor_positions()
        self.cursor_moved.emit("voltage", cursor_id + 1, value)

    def show_measurement_highlight(self, h_lines: list[float],
                                    v_lines: list[float],
                                    color: str = "#ffffff"):
        """Show temporary dashed highlight lines on the plot.

        Used when hovering over a measurement value to visualize it.

        Args:
            h_lines: Y-positions for horizontal highlight lines (voltages).
            v_lines: X-positions for vertical highlight lines (times).
            color: Line color (defaults to white).
        """
        self.hide_measurement_highlight()  # Remove any previous
        pen = pg.mkPen(color, width=1.0, style=Qt.PenStyle.DashLine)
        for y in h_lines:
            line = pg.InfiniteLine(pos=y, angle=0, pen=pen)
            self.addItem(line)
            self._highlight_lines.append(line)
        for x in v_lines:
            line = pg.InfiniteLine(pos=x, angle=90, pen=pen)
            self.addItem(line)
            self._highlight_lines.append(line)

    def hide_measurement_highlight(self):
        """Remove all measurement highlight lines."""
        for line in self._highlight_lines:
            self.removeItem(line)
        self._highlight_lines.clear()

    def update_waveform(self, waveform: WaveformData):
        """Update a channel's waveform display.

        Args:
            waveform: Processed waveform data with voltage and time arrays.
        """
        ch = waveform.channel

        # Ignore data for disabled channels (queued signals can arrive late)
        if ch not in self._enabled_channels:
            return

        # Auto-create trace if not exists
        if ch not in self._traces:
            color = self._colors.get(ch, channel_color(ch))
            trace = self.plot([], [], pen=pg.mkPen(color=color, width=1.5))
            self._traces[ch] = trace
            self._create_gnd_marker(ch)

        # Cache raw data (scope-space) for instant replotting when scales change
        self._raw_waveforms[ch] = (waveform.time_axis, waveform.voltage)

        # Scale scope-space voltage to display coordinates.
        # _voltage_scale includes both inter-channel V/div normalization
        # and probe attenuation compensation.
        scale = self._voltage_scale(ch)
        if scale != 1.0:
            display_voltage = waveform.voltage * scale
        else:
            display_voltage = waveform.voltage

        self._traces[ch].setData(waveform.time_axis, display_voltage)

        # Show trigger crossing marker on the trigger source channel.
        # Only the trigger source waveform has trigger_sample set.
        idx = waveform.trigger_sample
        if (idx is not None
                and 0 <= idx < len(waveform.time_axis) - 1):
            # Interpolate between sample[idx] and sample[idx+1] to find
            # the exact point where voltage = trigger level.  The crossing
            # happens BETWEEN these two samples.  Both voltage[] and
            # trigger_level are in scope-space, so they compare directly.
            v0 = waveform.voltage[idx]
            v1 = waveform.voltage[idx + 1]
            t0 = waveform.time_axis[idx]
            t1 = waveform.time_axis[idx + 1]
            dv = v1 - v0
            if abs(dv) > 1e-12:
                # Trigger level in scope-space (with offset baked in)
                screen_level = self._trigger_level + self._trigger_source_offset
                frac = (screen_level - v0) / dv
                frac = max(0.0, min(1.0, frac))  # clamp
                cross_t = t0 + frac * (t1 - t0)
                # Position dot in display space (scaled from scope-space)
                cross_v = screen_level * scale
            else:
                # Flat segment — place at midpoint (in display space)
                cross_t = (t0 + t1) / 2
                cross_v = ((v0 + v1) / 2) * scale

            self._trigger_crossing_ch = ch
            if self._trigger_crossing_dot is not None:
                self._trigger_crossing_dot.setData(
                    pos=np.array([[cross_t, cross_v]])
                )
                self._trigger_crossing_dot.setVisible(True)
            if self._trigger_crossing_label is not None:
                self._trigger_crossing_label.setHtml(
                    self._crossing_label_html(self._trigger_slope)
                )
                # Offset label above and right of the dot
                label_offset_y = 0.25 * self._v_per_div
                label_offset_x = 0.15 * self._t_per_div
                self._trigger_crossing_label.setPos(
                    cross_t + label_offset_x, cross_v + label_offset_y
                )
                self._trigger_crossing_label.setVisible(True)
        elif idx is None and ch == self._trigger_crossing_ch:
            # Trigger source channel arrived without crossing (AUTO) — hide
            self._trigger_crossing_ch = None
            if self._trigger_crossing_dot is not None:
                self._trigger_crossing_dot.setVisible(False)
            if self._trigger_crossing_label is not None:
                self._trigger_crossing_label.setVisible(False)

    def clear_channel(self, channel: int):
        """Clear waveform data for a channel."""
        if channel in self._traces:
            self._traces[channel].setData([], [])
        self._raw_waveforms.pop(channel, None)

    def clear_all(self):
        """Clear all waveform data."""
        for trace in self._traces.values():
            trace.setData([], [])
        self._raw_waveforms.clear()

    # --- Coordinate conversion helpers ---

    def _data_to_widget_y(self, y_data: float) -> float:
        """Convert a Y data coordinate to widget pixel Y."""
        vb = self.getPlotItem().getViewBox()
        scene_pt = vb.mapViewToScene(QPointF(0, y_data))
        return self.mapFromScene(scene_pt).y()

    def _data_to_widget_x(self, x_data: float) -> float:
        """Convert an X data coordinate to widget pixel X."""
        vb = self.getPlotItem().getViewBox()
        scene_pt = vb.mapViewToScene(QPointF(x_data, 0))
        return self.mapFromScene(scene_pt).x()

    def _widget_to_data(self, widget_point: QPoint) -> QPointF:
        """Convert widget pixel coordinates to data coordinates."""
        vb = self.getPlotItem().getViewBox()
        return vb.mapSceneToView(self.mapToScene(widget_point))

    # --- Drag interactions (markers + zoom) ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            px_x = pos.x()
            px_y = pos.y()
            th = self._HIT_THRESHOLD_PX

            # 1. Trigger level line (Y proximity anywhere on X)
            trig_scale = self._voltage_scale(self._trigger_source_ch)
            trig_screen_y = (self._trigger_level + self._trigger_source_offset) * trig_scale
            trig_level_py = self._data_to_widget_y(trig_screen_y)
            if abs(px_y - trig_level_py) < th:
                self._dragging = 'trigger_level'
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                event.accept()
                return

            # 2. Trigger position ▼ marker (near top edge)
            trig_pos_px = self._data_to_widget_x(self._trigger_pos)
            top_y = (self.NUM_V_DIVS / 2) * self._v_per_div
            marker_py = self._data_to_widget_y(top_y)
            if abs(px_x - trig_pos_px) < th and abs(px_y - marker_py) < th * 3:
                self._dragging = 'trigger_pos'
                self._drag_prev_px = pos
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return

            # 3. GND markers (left edge badges)
            left_x = self._h_position - (self.NUM_H_DIVS / 2) * self._t_per_div
            left_px = self._data_to_widget_x(left_x)
            for ch in self._gnd_markers:
                offset = self._channel_offsets.get(ch, 0.0)
                # GND markers are displayed at scaled offset positions
                marker_py = self._data_to_widget_y(offset * self._voltage_scale(ch))
                if abs(px_x - left_px) < th * 4 and abs(px_y - marker_py) < th * 2:
                    self._dragging = ('offset', ch)
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                    event.accept()
                    return

            # 4. Cursor lines (if visible)
            if self._cursor_mode in ("time", "both"):
                for i in range(2):
                    if self._time_cursor_lines[i] is not None:
                        cursor_px = self._data_to_widget_x(self._time_cursors[i])
                        if abs(px_x - cursor_px) < th:
                            self._dragging = ('cursor_time', i)
                            self.setCursor(Qt.CursorShape.SizeHorCursor)
                            event.accept()
                            return

            if self._cursor_mode in ("voltage", "both"):
                for i in range(2):
                    if self._volt_cursor_lines[i] is not None:
                        cursor_py = self._data_to_widget_y(self._volt_cursors[i])
                        if abs(px_y - cursor_py) < th:
                            self._dragging = ('cursor_volt', i)
                            self.setCursor(Qt.CursorShape.SizeVerCursor)
                            event.accept()
                            return

            # 5. Default: start zoom rectangle
            self._zoom_origin = pos

        # Never forward mouse presses to PyQtGraph
        event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()

        # --- Marker drag handling ---
        if self._dragging == 'trigger_level':
            data_pt = self._widget_to_data(pos)
            # Reverse-scale from display space to the trigger source
            # channel's scope-space voltage, then subtract source offset.
            trig_scale = self._voltage_scale(self._trigger_source_ch)
            if trig_scale > 0:
                new_level = data_pt.y() / trig_scale - self._trigger_source_offset
            else:
                new_level = data_pt.y() - self._trigger_source_offset
            self._trigger_level = new_level
            self._update_trigger_level_position()
            if self._trigger_level_badge is not None:
                self._trigger_level_badge.setHtml(
                    self._trigger_badge_html(new_level)
                )
            self.trigger_level_dragged.emit(new_level)
            event.accept()
            return

        if self._dragging == 'trigger_pos':
            # Pixel-delta approach: shift h_position by how far mouse moved
            dx_px = pos.x() - self._drag_prev_px.x()
            self._drag_prev_px = pos
            vb = self.getPlotItem().getViewBox()
            view_range = vb.viewRange()
            x_span = view_range[0][1] - view_range[0][0]
            data_delta = dx_px * (x_span / self.viewport().width())
            self._h_position -= data_delta
            self._update_axis_range()
            self.trigger_pos_dragged.emit(self._h_position)
            event.accept()
            return

        if isinstance(self._dragging, tuple) and self._dragging[0] == 'offset':
            ch = self._dragging[1]
            data_pt = self._widget_to_data(pos)
            # Reverse-scale from display space to the channel's scope-space
            # voltage so the SCPI offset stays in scope-space volts.
            scale = self._voltage_scale(ch)
            new_offset = data_pt.y() / scale if scale > 0 else data_pt.y()
            self._channel_offsets[ch] = new_offset
            self._update_gnd_positions()
            self.offset_dragged.emit(ch, new_offset)
            event.accept()
            return

        if isinstance(self._dragging, tuple) and self._dragging[0] == 'cursor_time':
            idx = self._dragging[1]
            data_pt = self._widget_to_data(pos)
            self.set_time_cursor(idx, data_pt.x())
            event.accept()
            return

        if isinstance(self._dragging, tuple) and self._dragging[0] == 'cursor_volt':
            idx = self._dragging[1]
            data_pt = self._widget_to_data(pos)
            self.set_volt_cursor(idx, data_pt.y())
            event.accept()
            return

        # --- Zoom rubber band ---
        if self._zoom_origin is not None:
            dx = pos.x() - self._zoom_origin.x()
            dy = pos.y() - self._zoom_origin.y()
            if abs(dx) >= self.MIN_DRAG_PX or abs(dy) >= self.MIN_DRAG_PX:
                if self._rubber_band is None:
                    self._rubber_band = QRubberBand(
                        QRubberBand.Shape.Rectangle, self.viewport()
                    )
                self._rubber_band.setGeometry(
                    QRect(self._zoom_origin, pos).normalized()
                )
                self._rubber_band.show()

        # Never forward mouse moves to PyQtGraph
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # End marker drag
            if self._dragging is not None:
                self._dragging = None
                self._drag_prev_px = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return

            # End zoom rectangle
            if self._zoom_origin is not None:
                pos = event.position().toPoint()
                dx = pos.x() - self._zoom_origin.x()
                dy = pos.y() - self._zoom_origin.y()

                if self._rubber_band is not None:
                    self._rubber_band.hide()
                    self._rubber_band.deleteLater()
                    self._rubber_band = None

                if abs(dx) >= self.MIN_DRAG_PX or abs(dy) >= self.MIN_DRAG_PX:
                    vb = self.getPlotItem().getViewBox()
                    p1 = vb.mapSceneToView(self.mapToScene(self._zoom_origin))
                    p2 = vb.mapSceneToView(self.mapToScene(pos))
                    t_min = min(p1.x(), p2.x())
                    t_max = max(p1.x(), p2.x())
                    v_min = min(p1.y(), p2.y())
                    v_max = max(p1.y(), p2.y())
                    self.zoom_requested.emit(t_min, v_min, t_max, v_max)

                self._zoom_origin = None

        # Never forward mouse releases to PyQtGraph
        event.accept()

    # --- GND marker helpers ---

    def _create_gnd_marker(self, channel: int):
        """Create a GND badge on the left edge for a channel.

        Renders as a bordered, colored label: CH ▶  (or CH ▶ 10x with probe)
        Positioned at the left plot edge, at the channel's 0V offset.
        """
        if channel in self._gnd_markers:
            return  # Already exists

        color = self._colors.get(channel, channel_color(channel))
        left_x = self._h_position - (self.NUM_H_DIVS / 2) * self._t_per_div
        offset = self._channel_offsets.get(channel, 0.0)

        # Include probe factor in label when != 1x
        probe = self._probe_factors.get(channel, 1.0)
        if probe != 1.0:
            label = (f'{channel} ▶ '
                     f'<span style="font-size:9px;">{probe:g}x</span>')
        else:
            label = f"{channel} ▶"

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
            f'">{label}</div>'
        )

        marker = pg.TextItem(html=html, anchor=(0.0, 0.5))
        marker.setPos(left_x, offset * self._voltage_scale(channel))
        self.addItem(marker)
        self._gnd_markers[channel] = marker

    def _remove_gnd_marker(self, channel: int):
        """Remove a channel's GND marker."""
        if channel in self._gnd_markers:
            self.removeItem(self._gnd_markers[channel])
            del self._gnd_markers[channel]
