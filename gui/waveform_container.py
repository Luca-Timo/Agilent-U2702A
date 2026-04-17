"""
Waveform container — wraps WaveformWidget with optional split-channel layout.

Two modes:
  - "combined" (default): all channels overlaid in single WaveformWidget
  - "split": separate plot pane per enabled channel, stacked vertically

The container forwards all WaveformWidget signals and public methods.

The FFT pane lives at the container level (above this file's two display
widgets), so it's available in both modes. The user can resize the
divider between the waveform area and the FFT pane via the QSplitter.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QStackedWidget, QSplitter, QVBoxLayout, QWidget,
)

from gui.theme import (
    BG_PLOT, GRID_COLOR, TEXT_DIM, NUM_CHANNELS, channel_color,
    format_vdiv, format_frequency, MATH_COLOR, MATH_CH,
)
from gui.waveform_widget import WaveformWidget
from processing.waveform import WaveformData


class SplitPaneManager:
    """Manages the split-view GraphicsLayoutWidget with per-channel plot panes."""

    def __init__(self, parent_widget: QWidget):
        self._parent = parent_widget
        self._layout_widget = pg.GraphicsLayoutWidget(parent=parent_widget)
        self._layout_widget.setBackground(BG_PLOT)

        # Per-channel plot items: {ch: PlotItem}
        self._panes: dict[int, pg.PlotItem] = {}
        self._traces: dict[int, pg.PlotDataItem] = {}
        self._enabled: dict[int, bool] = {}
        self._colors: dict[int, str] = {}
        self._vdivs: dict[int, float] = {}
        self._offsets: dict[int, float] = {}
        self._probes: dict[int, float] = {}
        self._inverted: dict[int, bool] = {}

        # Extra panes
        self._fft_pane: pg.PlotItem | None = None
        self._fft_trace: pg.PlotDataItem | None = None
        self._fft_requested: bool = False
        self._math_pane: pg.PlotItem | None = None
        self._math_trace: pg.PlotDataItem | None = None
        self._math_requested: bool = False

        # Reference traces: {ch: PlotDataItem}
        self._ref_traces: dict[int, pg.PlotDataItem] = {}

        # GND markers: {ch: TextItem}
        self._gnd_markers: dict[int, pg.TextItem] = {}

        # Shared time range
        self._t_per_div = 1e-3
        self._h_position = 0.0
        self._v_per_div = 1.0  # master V/div from combined mode

        # Trigger state
        self._trigger_source_ch: int = 1
        self._trigger_level: float = 0.0
        self._trigger_source_offset: float = 0.0
        self._trigger_pos: float = 0.0  # trigger time position (seconds)
        self._trigger_level_line: pg.InfiniteLine | None = None
        self._trigger_level_badge: pg.TextItem | None = None
        self._trigger_pos_markers: dict[int, pg.ScatterPlotItem] = {}  # per-pane ▼

        # Cursor state
        self._cursor_mode: str = "off"
        self._cursor_channel: int = 1
        self._time_cursors: list[float] = [0.0, 0.0]
        self._volt_cursors: list[float] = [0.0, 0.0]
        self._time_cursor_lines: dict[int, list[pg.InfiniteLine]] = {}  # {ch: [line0, line1]}
        self._volt_cursor_lines: list[pg.InfiniteLine | None] = [None, None]

        for ch in range(1, NUM_CHANNELS + 1):
            self._enabled[ch] = False
            self._colors[ch] = channel_color(ch)
            self._vdivs[ch] = 1.0
            self._offsets[ch] = 0.0
            self._probes[ch] = 1.0
            self._inverted[ch] = False

    @property
    def widget(self) -> pg.GraphicsLayoutWidget:
        return self._layout_widget

    def _get_pane(self, ch: int) -> pg.PlotItem | None:
        """Get the plot pane for a channel, including MATH_CH."""
        pane = self._panes.get(ch)
        if pane is None and ch == MATH_CH:
            pane = self._math_pane
        return pane

    def rebuild(self):
        """Rebuild the split layout from current state."""
        self._layout_widget.clear()
        self._panes.clear()
        self._traces.clear()
        self._fft_pane = None
        self._fft_trace = None
        self._math_pane = None
        self._math_trace = None
        self._trigger_level_line = None
        self._trigger_level_badge = None
        self._trigger_pos_markers.clear()
        self._time_cursor_lines.clear()
        self._volt_cursor_lines = [None, None]
        self._gnd_markers.clear()

        row = 0
        prev_pane = None

        for ch in range(1, NUM_CHANNELS + 1):
            if not self._enabled.get(ch, False):
                continue

            pane = self._layout_widget.addPlot(row=row, col=0)
            self._setup_pane(pane, f"CH{ch}", self._colors[ch])
            self._panes[ch] = pane

            trace = pane.plot(pen=pg.mkPen(self._colors[ch], width=1.5))
            self._traces[ch] = trace

            # GND marker on left edge
            self._create_gnd_marker(ch, pane)

            # Link X axes
            if prev_pane is not None:
                pane.setXLink(prev_pane)
            prev_pane = pane

            self._update_pane_range(ch)
            self._update_pane_label(ch)
            row += 1

        # Re-add math pane if it was enabled before rebuild
        if self._math_requested:
            self.add_math_pane()

        # Re-add FFT pane if it was enabled before rebuild
        if self._fft_requested:
            self.add_fft_pane()

        # Recreate trigger and cursor overlays on the new panes
        self._rebuild_trigger_overlay()
        self._rebuild_cursor_overlays()

        if not self._panes:
            # No channels enabled — show empty placeholder
            placeholder = self._layout_widget.addPlot(row=0, col=0)
            self._setup_pane(placeholder, "No channels", "#666666")

    def _setup_pane(self, pane: pg.PlotItem, label: str, color: str):
        """Configure a split pane with dark theme styling."""
        pane.setMenuEnabled(False)
        pane.hideButtons()
        pane.showGrid(x=True, y=True, alpha=0.15)
        pane.getAxis("left").setPen(pg.mkPen(color))
        pane.getAxis("left").setTextPen(pg.mkPen(TEXT_DIM))
        pane.getAxis("bottom").setTextPen(pg.mkPen(TEXT_DIM))
        pane.getAxis("bottom").setPen(pg.mkPen(GRID_COLOR))
        pane.setLabel("left", label, color=color, size="9pt")
        # Disable mouse interaction (zoom/pan handled by main widget)
        pane.setMouseEnabled(x=False, y=False)

    def _update_pane_range(self, ch: int):
        """Update Y range for a channel pane (or math pane for MATH_CH).

        _vdivs stores the effective V/div (raw × probe) already set by
        the container, so we must NOT multiply by probe again here.
        The waveform data is plotted as voltage × probe (probe-tip space),
        and the Y range must match that space.
        """
        pane = self._panes.get(ch)
        if pane is None and ch == MATH_CH:
            pane = self._math_pane
        if pane is None:
            return
        eff_vdiv = self._vdivs.get(ch, 1.0)  # already includes probe
        probe = self._probes.get(ch, 1.0)
        offset = self._offsets.get(ch, 0.0)
        n_divs = 4  # ±4 divisions per pane
        half_range = eff_vdiv * n_divs
        center = offset * probe  # offset is raw scope value, scale to probe-tip
        pane.setYRange(center - half_range, center + half_range, padding=0)

        # Update X range
        half_t = self._t_per_div * 5  # 10 divisions
        center_t = self._h_position
        pane.setXRange(center_t - half_t, center_t + half_t, padding=0)

    def update_waveform(self, waveform: WaveformData):
        """Update a channel's trace in its split pane."""
        ch = waveform.channel
        trace = self._traces.get(ch)
        if trace is None:
            return

        voltage = waveform.voltage
        if self._inverted.get(ch, False):
            voltage = -voltage

        probe = self._probes.get(ch, 1.0)
        trace.setData(waveform.time_axis, voltage * probe)

    def set_channel_enabled(self, ch: int, enabled: bool):
        self._enabled[ch] = enabled

    def set_channel_vdiv(self, ch: int, effective_vdiv: float):
        self._vdivs[ch] = effective_vdiv
        self._update_pane_range(ch)
        self._update_pane_label(ch)
        self._update_trigger_pos_markers()

    def set_channel_offset(self, ch: int, offset: float):
        self._offsets[ch] = offset
        self._update_pane_range(ch)
        self._update_gnd_positions()
        self._update_trigger_pos_markers()

    def set_channel_probe(self, ch: int, factor: float):
        self._probes[ch] = factor
        self._update_pane_range(ch)
        # Rebuild GND marker to update probe label
        pane = self._panes.get(ch)
        if pane is not None and ch in self._gnd_markers:
            pane.removeItem(self._gnd_markers[ch])
            del self._gnd_markers[ch]
            self._create_gnd_marker(ch, pane)

    def set_channel_color(self, ch: int, color: str):
        self._colors[ch] = color
        trace = self._traces.get(ch)
        if trace:
            trace.setPen(pg.mkPen(color, width=1.5))
        pane = self._panes.get(ch)
        if pane:
            pane.getAxis("left").setPen(pg.mkPen(color))
            pane.setLabel("left", f"CH{ch}", color=color, size="9pt")

    def set_channel_inverted(self, ch: int, inverted: bool):
        self._inverted[ch] = inverted

    # ------------------------------------------------------------------
    #  GND markers
    # ------------------------------------------------------------------

    def _update_pane_label(self, ch: int):
        """Update the Y-axis label to show channel name and V/div."""
        pane = self._panes.get(ch)
        if pane is None:
            return
        color = self._colors.get(ch, channel_color(ch))
        eff_vdiv = self._vdivs.get(ch, 1.0)
        label = f"CH{ch}  {format_vdiv(eff_vdiv)}"
        pane.setLabel("left", label, color=color, size="9pt")

    def _create_gnd_marker(self, ch: int, pane: pg.PlotItem):
        """Create a GND badge on the left edge of a channel pane."""
        color = self._colors.get(ch, channel_color(ch))
        probe = self._probes.get(ch, 1.0)
        if probe != 1.0:
            label = (f'{ch} ▶ '
                     f'<span style="font-size:9px;">{probe:g}x</span>')
        else:
            label = f"{ch} ▶"

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
        offset = self._offsets.get(ch, 0.0)
        left_x = self._h_position - self._t_per_div * 5
        marker.setPos(left_x, offset * probe)
        pane.addItem(marker)
        self._gnd_markers[ch] = marker

    def _update_gnd_positions(self):
        """Reposition all GND markers (e.g., after offset or axis change)."""
        left_x = self._h_position - self._t_per_div * 5
        for ch, marker in self._gnd_markers.items():
            probe = self._probes.get(ch, 1.0)
            offset = self._offsets.get(ch, 0.0)
            marker.setPos(left_x, offset * probe)

    # ------------------------------------------------------------------
    #  Trigger overlays
    # ------------------------------------------------------------------

    def set_trigger_source_channel(self, ch: int):
        self._trigger_source_ch = ch
        self._rebuild_trigger_overlay()

    def set_trigger_level(self, level: float):
        self._trigger_level = level
        self._update_trigger_overlay_pos()

    def set_trigger_source_offset(self, offset: float):
        self._trigger_source_offset = offset
        self._update_trigger_overlay_pos()

    def set_trigger_position(self, time_pos: float):
        self._trigger_pos = time_pos
        self._update_trigger_pos_markers()

    def _rebuild_trigger_overlay(self):
        """Remove old trigger overlay and create on the source channel pane."""
        all_panes = list(self._panes.values()) + ([self._math_pane] if self._math_pane else [])

        # Remove old level line + badge from ALL panes
        if self._trigger_level_line is not None:
            for pane in all_panes:
                try:
                    pane.removeItem(self._trigger_level_line)
                except Exception:
                    pass
        if self._trigger_level_badge is not None:
            for pane in all_panes:
                try:
                    pane.removeItem(self._trigger_level_badge)
                except Exception:
                    pass
        self._trigger_level_line = None
        self._trigger_level_badge = None

        # Remove old position markers (▼) from all panes
        for ch, marker in self._trigger_pos_markers.items():
            pane = self._panes.get(ch)
            if pane is not None:
                try:
                    pane.removeItem(marker)
                except Exception:
                    pass
        self._trigger_pos_markers.clear()

        TRIGGER_COLOR = "#FF4444"

        # --- Trigger position marker (▼ at top of each pane) ---
        for ch, pane in self._panes.items():
            eff_vdiv = self._vdivs.get(ch, 1.0)
            top_y = eff_vdiv * 4  # top edge of pane (n_divs=4)
            offset = self._offsets.get(ch, 0.0)
            probe = self._probes.get(ch, 1.0)
            marker_y = offset * probe + top_y * 0.95  # just below top edge
            marker = pg.ScatterPlotItem(
                pos=np.array([[self._trigger_pos, marker_y]]),
                symbol='t',  # downward-pointing triangle
                size=12,
                pen=pg.mkPen(TRIGGER_COLOR, width=1),
                brush=pg.mkBrush(TRIGGER_COLOR),
            )
            marker.setZValue(1002)
            pane.addItem(marker)
            self._trigger_pos_markers[ch] = marker

        # --- Trigger level line + badge on source channel pane ---
        pane = self._panes.get(self._trigger_source_ch)
        if pane is None:
            self._update_trigger_pos_markers()
            return

        self._trigger_level_line = pg.InfiniteLine(
            angle=0,
            pen=pg.mkPen(TRIGGER_COLOR, width=1.5, style=Qt.PenStyle.DashLine),
        )
        self._trigger_level_line.setZValue(1000)
        pane.addItem(self._trigger_level_line)

        self._trigger_level_badge = pg.TextItem(anchor=(1.0, 0.5))
        self._trigger_level_badge.setZValue(1001)
        pane.addItem(self._trigger_level_badge)

        self._update_trigger_overlay_pos()
        self._update_trigger_pos_markers()

    def _update_trigger_overlay_pos(self):
        """Reposition trigger level line and badge in the source pane."""
        if self._trigger_level_line is None:
            return
        ch = self._trigger_source_ch
        probe = self._probes.get(ch, 1.0)
        level_display = (self._trigger_level + self._trigger_source_offset) * probe
        self._trigger_level_line.setValue(level_display)

        if self._trigger_level_badge is not None:
            from gui.theme import format_voltage
            TRIGGER_COLOR = "#FF4444"
            text = format_voltage(self._trigger_level * probe)
            self._trigger_level_badge.setHtml(
                f'<div style="background-color:{TRIGGER_COLOR};color:#fff;'
                f'border-radius:2px;padding:1px 4px;font-size:9px;'
                f'font-weight:bold;font-family:Menlo,monospace;">'
                f'T ◀ {text}</div>'
            )
            # Use stored time range instead of viewRange() which may be stale
            right_x = self._h_position + self._t_per_div * 5
            self._trigger_level_badge.setPos(right_x, level_display)

    def _update_trigger_pos_markers(self):
        """Reposition the ▼ trigger position markers at the top of each pane."""
        for ch, marker in self._trigger_pos_markers.items():
            eff_vdiv = self._vdivs.get(ch, 1.0)
            offset = self._offsets.get(ch, 0.0)
            probe = self._probes.get(ch, 1.0)
            top_y = offset * probe + eff_vdiv * 4 * 0.95
            marker.setData(pos=np.array([[self._trigger_pos, top_y]]))

    # ------------------------------------------------------------------
    #  Cursor overlays
    # ------------------------------------------------------------------

    def set_cursor_mode(self, mode: str):
        self._cursor_mode = mode
        self._rebuild_cursor_overlays()

    def set_cursor_channel(self, ch: int):
        self._cursor_channel = ch
        self._rebuild_cursor_overlays()

    def set_time_cursor(self, cursor_id: int, value: float):
        self._time_cursors[cursor_id] = value
        self._update_cursor_positions()

    def set_volt_cursor(self, cursor_id: int, value: float):
        self._volt_cursors[cursor_id] = value
        self._update_cursor_positions()

    def _rebuild_cursor_overlays(self):
        """Remove and recreate cursor lines based on current mode."""
        CURSOR_COLOR = "#FF8800"

        # Remove old time cursor lines from all panes
        for ch, lines in self._time_cursor_lines.items():
            pane = self._get_pane(ch)
            if pane is None:
                continue
            for line in lines:
                try:
                    pane.removeItem(line)
                except Exception:
                    pass
        self._time_cursor_lines.clear()

        # Remove old voltage cursor lines
        all_removable = list(self._panes.values())
        if self._math_pane is not None:
            all_removable.append(self._math_pane)
        for vline in self._volt_cursor_lines:
            if vline is not None:
                for pane in all_removable:
                    try:
                        pane.removeItem(vline)
                    except Exception:
                        pass
        self._volt_cursor_lines = [None, None]

        show_time = self._cursor_mode in ("time", "both")
        show_volt = self._cursor_mode in ("voltage", "both")

        styles = [
            pg.mkPen(CURSOR_COLOR, width=1.2, style=Qt.PenStyle.SolidLine),
            pg.mkPen(CURSOR_COLOR, width=1.2, style=Qt.PenStyle.DashDotLine),
        ]

        # Time cursors — add vertical lines to every channel pane (incl. math)
        if show_time:
            all_ch_panes = dict(self._panes)
            if self._math_pane is not None:
                all_ch_panes[MATH_CH] = self._math_pane
            for ch, pane in all_ch_panes.items():
                lines = []
                for i in range(2):
                    line = pg.InfiniteLine(
                        pos=self._time_cursors[i], angle=90, pen=styles[i])
                    pane.addItem(line)
                    lines.append(line)
                self._time_cursor_lines[ch] = lines

        # Voltage cursors — horizontal lines on the cursor channel pane
        if show_volt:
            pane = self._get_pane(self._cursor_channel)
            if pane is not None:
                for i in range(2):
                    line = pg.InfiniteLine(
                        pos=self._volt_cursors[i], angle=0, pen=styles[i])
                    pane.addItem(line)
                    self._volt_cursor_lines[i] = line

        self._update_cursor_positions()

    def _display_to_split_y(self, display_y: float) -> float:
        """Convert a combined-mode display-space Y value to split-pane space.

        Combined mode: y = voltage × (v_per_div / eff_vdiv) × probe
        Split pane:    y = voltage × probe
        Conversion:    split_y = display_y × (eff_vdiv / v_per_div)
        """
        ch = self._cursor_channel
        eff_vdiv = self._vdivs.get(ch, 1.0)
        if abs(self._v_per_div) < 1e-15:
            return display_y
        return display_y * eff_vdiv / self._v_per_div

    def _update_cursor_positions(self):
        """Move cursor lines to their current positions."""
        # Time cursors
        for ch, lines in self._time_cursor_lines.items():
            for i, line in enumerate(lines):
                line.setValue(self._time_cursors[i])

        # Voltage cursors — convert from display-space to split-pane space
        for i, line in enumerate(self._volt_cursor_lines):
            if line is not None:
                line.setValue(self._display_to_split_y(self._volt_cursors[i]))

    def set_scales(self, v_per_div: float, t_per_div: float):
        self._v_per_div = v_per_div
        self._t_per_div = t_per_div
        for ch in self._panes:
            self._update_pane_range(ch)
        self._update_gnd_positions()
        self._update_trigger_overlay_pos()

    def set_h_position(self, pos: float):
        self._h_position = pos
        for ch in self._panes:
            self._update_pane_range(ch)
        self._update_gnd_positions()
        self._update_trigger_overlay_pos()

    # --- FFT pane (superseded) ---
    # These methods used to host the FFT trace inside the split
    # GraphicsLayoutWidget. The FFT pane now lives at the
    # ``WaveformContainer`` level so it's available in both combined
    # and split modes — kept here only so ``_fft_requested`` state
    # doesn't crash callers; nothing invokes them today.

    def add_fft_pane(self):
        """Add an FFT pane at the bottom of the split layout."""
        self._fft_requested = True
        if self._fft_pane is not None:
            return
        row = self._layout_widget.ci.layout.rowCount()
        pane = self._layout_widget.addPlot(row=row, col=0)
        self._setup_pane(pane, "FFT", "#aaaaaa")
        pane.setLabel("bottom", "Frequency", units="Hz")
        # FFT has independent X axis (not linked)
        self._fft_pane = pane
        self._fft_trace = pane.plot(pen=pg.mkPen("#ffffff", width=1.2))

    def remove_fft_pane(self):
        self._fft_requested = False
        if self._fft_pane is not None:
            self._layout_widget.removeItem(self._fft_pane)
            self._fft_pane = None
            self._fft_trace = None

    def update_fft(self, freq: np.ndarray, magnitude: np.ndarray, scale: str = "dbv"):
        """Update FFT trace data."""
        if self._fft_trace is None:
            return
        self._fft_trace.setData(freq, magnitude)
        label = "dBV" if scale == "dbv" else "V"
        self._fft_pane.setLabel("left", f"FFT ({label})", color="#aaaaaa", size="9pt")

    # --- Math pane ---

    def add_math_pane(self):
        """Add a math pane between channel panes and FFT."""
        self._math_requested = True
        if self._math_pane is not None:
            return
        # Insert before FFT if present
        row = len([ch for ch in self._panes])
        pane = self._layout_widget.addPlot(row=row, col=0)
        self._setup_pane(pane, "Math", "#ff66ff")
        self._math_pane = pane
        self._math_trace = pane.plot(pen=pg.mkPen("#ff66ff", width=1.5))
        # Link X to channel panes
        first_pane = next(iter(self._panes.values()), None)
        if first_pane is not None:
            pane.setXLink(first_pane)
        # Apply stored V/div and offset
        self._update_pane_range(MATH_CH)

    def remove_math_pane(self):
        self._math_requested = False
        if self._math_pane is not None:
            self._layout_widget.removeItem(self._math_pane)
            self._math_pane = None
            self._math_trace = None

    def update_math(self, time_axis: np.ndarray, voltage: np.ndarray, label: str = "Math"):
        """Update math trace data."""
        if self._math_trace is None:
            return
        self._math_trace.setData(time_axis, voltage)
        self._math_pane.setLabel("left", label, color="#ff66ff", size="9pt")

    # --- Reference waveforms ---

    def update_reference(self, ch: int, time_axis: np.ndarray, voltage: np.ndarray, visible: bool = True):
        """Show/update a reference waveform in a channel's pane."""
        pane = self._panes.get(ch)
        if pane is None:
            return

        if ch in self._ref_traces:
            pane.removeItem(self._ref_traces[ch])
            del self._ref_traces[ch]

        if visible and len(voltage) > 0:
            color = QColor(self._colors.get(ch, "#888888"))
            color.setAlpha(128)
            pen = pg.mkPen(color, width=1.0, style=Qt.PenStyle.DashLine)
            ref_trace = pane.plot(time_axis, voltage, pen=pen)
            self._ref_traces[ch] = ref_trace

    def clear_references(self):
        for ch, trace in list(self._ref_traces.items()):
            pane = self._panes.get(ch)
            if pane:
                pane.removeItem(trace)
        self._ref_traces.clear()

    def clear_channel(self, ch: int):
        trace = self._traces.get(ch)
        if trace:
            trace.setData([], [])

    def clear_all(self):
        for trace in self._traces.values():
            trace.setData([], [])


# Need QColor for reference traces
from PySide6.QtGui import QColor


class WaveformContainer(QWidget):
    """Container that switches between combined and split waveform display.

    In combined mode, delegates everything to the embedded WaveformWidget.
    In split mode, uses SplitPaneManager with per-channel plot panes.

    Signals are forwarded from the internal WaveformWidget.
    """

    # Forward signals from WaveformWidget
    zoom_requested = Signal(float, float, float, float)
    trigger_level_dragged = Signal(float)
    trigger_pos_dragged = Signal(float)
    offset_dragged = Signal(int, float)
    cursor_moved = Signal(str, int, float)

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__(parent)

        self._mode = "combined"  # "combined" or "split"

        # Combined mode — the existing WaveformWidget
        self._waveform = WaveformWidget(num_channels, parent=self)

        # Forward signals
        self._waveform.zoom_requested.connect(self.zoom_requested.emit)
        self._waveform.trigger_level_dragged.connect(self.trigger_level_dragged.emit)
        self._waveform.trigger_pos_dragged.connect(self.trigger_pos_dragged.emit)
        self._waveform.offset_dragged.connect(self.offset_dragged.emit)
        self._waveform.cursor_moved.connect(self.cursor_moved.emit)

        # Split mode manager
        self._split = SplitPaneManager(self)

        # Math uses virtual channel MATH_CH on the WaveformWidget
        self._math_enabled = False

        # -- Layout ------------------------------------------------
        # Top: a QStackedWidget that switches between combined view
        # (WaveformWidget) and split view (SplitPaneManager's
        # GraphicsLayoutWidget).
        # Bottom: an optional FFT plot that's visible when
        # add_fft_pane() has been called. Both panes live in a
        # vertical QSplitter so the user can resize the divider.
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._waveform)        # index 0
        self._stack.addWidget(self._split.widget)    # index 1
        self._stack.setCurrentIndex(0)

        self._fft_widget: pg.PlotWidget | None = None  # created lazily
        self._fft_scale: str = "dbv"

        self._vsplit = QSplitter(Qt.Orientation.Vertical, self)
        self._vsplit.setChildrenCollapsible(False)
        self._vsplit.addWidget(self._stack)
        # FFT widget is inserted into _vsplit on demand.

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self._vsplit)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def waveform_widget(self) -> WaveformWidget:
        """Direct access to the underlying WaveformWidget (for cursor state etc.)."""
        return self._waveform

    def set_layout_mode(self, mode: str):
        """Switch between 'combined' and 'split' display modes."""
        if mode == self._mode:
            return
        self._mode = mode
        if mode == "split":
            # Sync trigger/cursor state from combined widget before rebuild
            w = self._waveform
            self._split._trigger_source_ch = w._trigger_source_ch
            self._split._trigger_level = w._trigger_level
            self._split._trigger_source_offset = w._trigger_source_offset
            self._split._trigger_pos = w._trigger_pos
            self._split._cursor_mode = w._cursor_mode
            self._split._cursor_channel = w._cursor_channel
            self._split._time_cursors = list(w._time_cursors)
            self._split._volt_cursors = list(w._volt_cursors)
            self._split.rebuild()
            # Replay cached waveforms into the fresh split panes
            for ch, (t, v) in self._waveform._raw_waveforms.items():
                if ch == MATH_CH:
                    continue  # Math is replayed by _recompute_fft_math
                wf = WaveformData(
                    channel=ch,
                    raw_adc=np.array([], dtype=np.uint8),
                    voltage=v,
                    time_axis=t,
                    v_per_div=1.0,
                    offset=0.0,
                    t_per_div=0.0,
                    probe_factor=1.0,
                    timestamp=0.0,
                    trigger_sample=None,
                )
                self._split.update_waveform(wf)
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(0)

    # --- Delegate all WaveformWidget public methods ---
    # In combined mode: call WaveformWidget directly.
    # In split mode: also update split pane state.

    def update_waveform(self, waveform: WaveformData):
        self._waveform.update_waveform(waveform)
        if self._mode == "split":
            self._split.update_waveform(waveform)

    def set_scales(self, v_per_div: float, t_per_div: float):
        self._waveform.set_scales(v_per_div, t_per_div)
        self._split.set_scales(v_per_div, t_per_div)

    def set_h_position(self, position: float):
        self._waveform.set_h_position(position)
        self._split.set_h_position(position)

    def set_channel_vdiv(self, channel: int, effective_vdiv: float):
        self._waveform.set_channel_vdiv(channel, effective_vdiv)
        self._split.set_channel_vdiv(channel, effective_vdiv)

    def set_channel_enabled(self, channel: int, enabled: bool):
        self._waveform.set_channel_enabled(channel, enabled)
        self._split.set_channel_enabled(channel, enabled)
        if self._mode == "split":
            self._split.rebuild()

    def set_channel_offset(self, channel: int, offset: float):
        self._waveform.set_channel_offset(channel, offset)
        self._split.set_channel_offset(channel, offset)

    def set_channel_color(self, channel: int, color: str):
        self._waveform.set_channel_color(channel, color)
        self._split.set_channel_color(channel, color)

    def set_channel_probe(self, channel: int, factor: float):
        self._waveform.set_channel_probe(channel, factor)
        self._split.set_channel_probe(channel, factor)

    def set_channel_inverted(self, channel: int, inverted: bool):
        self._waveform.set_channel_inverted(channel, inverted)
        self._split.set_channel_inverted(channel, inverted)

    def set_channel_current_mode(self, channel: int, active: bool, shunt_r: float = 1.0):
        self._waveform.set_channel_current_mode(channel, active, shunt_r)

    def set_trigger_source_channel(self, channel: int):
        self._waveform.set_trigger_source_channel(channel)
        self._split.set_trigger_source_channel(channel)

    def set_trigger_position(self, time_pos: float):
        self._waveform.set_trigger_position(time_pos)
        self._split.set_trigger_position(time_pos)

    def set_trigger_level(self, level: float):
        self._waveform.set_trigger_level(level)
        self._split.set_trigger_level(level)

    def set_trigger_slope(self, slope: str):
        self._waveform.set_trigger_slope(slope)

    def set_trigger_source_offset(self, offset: float):
        self._waveform.set_trigger_source_offset(offset)
        self._split.set_trigger_source_offset(offset)

    def set_cursor_mode(self, mode: str):
        self._waveform.set_cursor_mode(mode)
        self._split.set_cursor_mode(mode)

    def set_time_cursor(self, cursor_id: int, value: float):
        self._waveform.set_time_cursor(cursor_id, value)
        self._split.set_time_cursor(cursor_id, value)

    def set_volt_cursor(self, cursor_id: int, value: float):
        self._waveform.set_volt_cursor(cursor_id, value)
        self._split.set_volt_cursor(cursor_id, value)

    def set_cursor_current_mode(self, active: bool, channel: int | None = None):
        self._waveform.set_cursor_current_mode(active, channel)
        if channel is not None:
            self._split.set_cursor_channel(channel)

    def reset_cursor_positions(self):
        self._waveform.reset_cursor_positions()

    def show_measurement_highlight(self, h_lines, v_lines, color="#ffffff"):
        self._waveform.show_measurement_highlight(h_lines, v_lines, color)

    def hide_measurement_highlight(self):
        self._waveform.hide_measurement_highlight()

    def clear_channel(self, channel: int):
        self._waveform.clear_channel(channel)
        self._split.clear_channel(channel)

    def clear_all(self):
        self._waveform.clear_all()
        self._split.clear_all()

    # --- FFT pane (container-level — works in combined AND split mode) ---

    def update_fft(self, freq: np.ndarray, magnitude: np.ndarray, scale: str = "dbv"):
        """Push a new frequency-domain trace to the FFT pane.

        No-op if the pane isn't currently shown — callers can safely
        invoke this every frame; ``add_fft_pane()`` controls visibility.
        """
        self._fft_scale = scale
        if self._fft_widget is None:
            return
        trace = getattr(self._fft_widget, "_fft_trace", None)
        if trace is None:
            return
        trace.setData(freq, magnitude)
        label = "dBV" if scale == "dbv" else "linear"
        self._fft_widget.setLabel(
            "left", f"FFT ({label})", color="#aaaaaa",
        )

    def add_fft_pane(self):
        """Reveal the FFT pane (creating it on first call)."""
        if self._fft_widget is None:
            self._fft_widget = self._build_fft_widget()
            self._vsplit.addWidget(self._fft_widget)
            # Give the waveform area ~70% and FFT ~30% by default;
            # user can drag to resize.
            self._vsplit.setSizes([700, 300])
            self._vsplit.setStretchFactor(0, 2)
            self._vsplit.setStretchFactor(1, 1)
        self._fft_widget.setVisible(True)

    def remove_fft_pane(self):
        """Hide the FFT pane. Kept alive so re-enabling is instant."""
        if self._fft_widget is not None:
            self._fft_widget.setVisible(False)

    def _build_fft_widget(self) -> pg.PlotWidget:
        """Create the FFT PlotWidget with scope-matching styling."""
        w = pg.PlotWidget(parent=self)
        w.setBackground(BG_PLOT)
        w.getAxis("bottom").setPen(pg.mkPen(GRID_COLOR))
        w.getAxis("left").setPen(pg.mkPen(GRID_COLOR))
        w.getAxis("bottom").setTextPen(pg.mkPen(TEXT_DIM))
        w.getAxis("left").setTextPen(pg.mkPen(TEXT_DIM))
        w.setLabel("bottom", "Frequency (Hz)", color="#aaaaaa")
        w.setLabel("left", "FFT", color="#aaaaaa")
        w.showGrid(x=True, y=True, alpha=0.2)
        w.setMouseEnabled(x=True, y=False)
        w.setMenuEnabled(False)
        # Stash the trace on the widget itself so update_fft can find it.
        # Use pg.mkPen (not QPen) so the pen is cosmetic — otherwise
        # pyqtgraph treats ``width=1`` as 1 data-unit (1 Hz / 1 dB)
        # and the line renders invisibly thin, leaving only the
        # sample points visible.
        w._fft_trace = w.plot(pen=pg.mkPen("#ffffff", width=1.2))
        w.setMinimumHeight(120)

        # --- Hover readout: vertical crosshair + freq/mag label ---
        # Snaps to the nearest FFT bin (x only — magnitude is taken
        # from the sample at that index rather than the mouse's y).
        hover_pen = pg.mkPen("#ffaa00", width=1, style=Qt.PenStyle.DashLine)
        w._hover_vline = pg.InfiniteLine(
            angle=90, movable=False, pen=hover_pen,
        )
        w._hover_vline.setVisible(False)
        w.addItem(w._hover_vline, ignoreBounds=True)

        w._hover_dot = pg.ScatterPlotItem(
            size=8,
            pen=pg.mkPen("#ffaa00", width=1.5),
            brush=pg.mkBrush("#ffaa00"),
        )
        w._hover_dot.setVisible(False)
        w.addItem(w._hover_dot, ignoreBounds=True)

        w._hover_text = pg.TextItem(
            text="", anchor=(0, 1), color=pg.mkColor("#ffcc66"),
            fill=pg.mkBrush(0, 0, 0, 180),
            border=pg.mkPen("#ffaa00", width=1),
        )
        w._hover_text.setVisible(False)
        w.addItem(w._hover_text, ignoreBounds=True)

        # sigMouseMoved emits scene coordinates; we map to data coords
        # inside the handler. Connect via the scene so we get events
        # even when the mouse is over the axes.
        w.scene().sigMouseMoved.connect(
            lambda pos, _w=w: self._on_fft_hover(_w, pos)
        )
        # Hide on leave — sigMouseMoved stops firing when the cursor
        # exits the widget, but the last-seen position leaves the
        # crosshair on screen. An event filter catches Leave.
        w.installEventFilter(self)
        w._hover_active = False

        return w

    def eventFilter(self, obj, event):
        """Hide the FFT hover readout when the mouse leaves the pane."""
        from PySide6.QtCore import QEvent
        if (self._fft_widget is not None
                and obj is self._fft_widget
                and event.type() == QEvent.Type.Leave):
            self._hide_fft_hover()
        return super().eventFilter(obj, event)

    def _on_fft_hover(self, widget: pg.PlotWidget, scene_pos):
        """Snap to the nearest FFT bin and show freq + magnitude."""
        trace = getattr(widget, "_fft_trace", None)
        if trace is None:
            self._hide_fft_hover()
            return
        freqs, mags = trace.getData()
        if freqs is None or len(freqs) == 0:
            self._hide_fft_hover()
            return

        vb = widget.plotItem.vb
        if not vb.sceneBoundingRect().contains(scene_pos):
            self._hide_fft_hover()
            return

        data_pt = vb.mapSceneToView(scene_pos)
        # Snap to the nearest FFT bin (frequencies are monotonic and
        # uniformly-ish spaced — ``searchsorted`` is O(log n)).
        x = data_pt.x()
        idx = int(np.clip(np.searchsorted(freqs, x), 1, len(freqs) - 1))
        # searchsorted returns the insertion point; pick whichever of
        # the two neighbours is closer.
        if abs(freqs[idx - 1] - x) < abs(freqs[idx] - x):
            idx -= 1
        sf = float(freqs[idx])
        sm = float(mags[idx])

        widget._hover_vline.setPos(sf)
        widget._hover_vline.setVisible(True)
        widget._hover_dot.setData([sf], [sm])
        widget._hover_dot.setVisible(True)

        unit = "dBV" if self._fft_scale == "dbv" else ""
        label = f"{format_frequency(sf)}\n{sm:.2f} {unit}".rstrip()
        widget._hover_text.setText(label)
        widget._hover_text.setPos(sf, sm)
        widget._hover_text.setVisible(True)
        widget._hover_active = True

    def _hide_fft_hover(self):
        w = self._fft_widget
        if w is None or not getattr(w, "_hover_active", False):
            return
        w._hover_vline.setVisible(False)
        w._hover_dot.setVisible(False)
        w._hover_text.setVisible(False)
        w._hover_active = False

    # --- Math (virtual channel MATH_CH on WaveformWidget) ---

    def update_math(self, time_axis: np.ndarray, voltage: np.ndarray, label: str = "Math"):
        # Combined mode: feed as virtual channel waveform
        if self._math_enabled:
            wf = WaveformData(
                channel=MATH_CH,
                raw_adc=np.array([], dtype=np.uint8),
                voltage=voltage,
                time_axis=time_axis,
                v_per_div=1.0,
                offset=0.0,
                t_per_div=0.0,
                probe_factor=1.0,
                timestamp=0.0,
                trigger_sample=None,
            )
            self._waveform.update_waveform(wf)
        # Split mode
        self._split.update_math(time_axis, voltage, label)

    def add_math_pane(self):
        self._math_enabled = True
        # Register math as virtual channel on WaveformWidget
        self._waveform.set_channel_color(MATH_CH, MATH_COLOR)
        self._waveform.set_channel_enabled(MATH_CH, True)
        self._waveform.set_channel_probe(MATH_CH, 1.0)
        # Split mode
        self._split.add_math_pane()

    def remove_math_pane(self):
        self._math_enabled = False
        self._waveform.set_channel_enabled(MATH_CH, False)
        self._split.remove_math_pane()

    def set_math_vdiv(self, vdiv: float):
        """Set math channel V/div for proper scaling."""
        self._waveform.set_channel_vdiv(MATH_CH, vdiv)
        self._split.set_channel_vdiv(MATH_CH, vdiv)

    def set_math_offset(self, offset: float):
        """Set math channel vertical offset."""
        self._waveform.set_channel_offset(MATH_CH, offset)
        self._split.set_channel_offset(MATH_CH, offset)

    def update_reference(self, ch: int, time_axis, voltage, visible=True):
        self._split.update_reference(ch, time_axis, voltage, visible)

    def clear_references(self):
        self._split.clear_references()

    # --- Attribute fallback for combined mode ---
    # Any attribute not found on WaveformContainer is looked up on WaveformWidget.
    # This catches internal state access (e.g., _cursor_mode, _time_cursors).

    def __getattr__(self, name):
        # Only fall through for attributes not on this instance
        # Avoid infinite recursion during init
        if name.startswith("__") or name in ("_waveform", "_split", "_mode", "_stack"):
            raise AttributeError(name)
        return getattr(self._waveform, name)
