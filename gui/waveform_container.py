"""
Waveform container — wraps WaveformWidget with optional split-channel layout.

Two modes:
  - "combined" (default): all channels overlaid in single WaveformWidget
  - "split": separate plot pane per enabled channel, stacked vertically

The container forwards all WaveformWidget signals and public methods.
In split mode, extra panes for FFT and math are available.
"""

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedLayout

from gui.theme import (
    BG_PLOT, GRID_COLOR, TEXT_DIM, NUM_CHANNELS, channel_color,
    format_vdiv, MATH_COLOR, MATH_CH,
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

        # Shared time range
        self._t_per_div = 1e-3
        self._h_position = 0.0
        self._v_per_div = 1.0  # master V/div from combined mode

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

    def rebuild(self):
        """Rebuild the split layout from current state."""
        self._layout_widget.clear()
        self._panes.clear()
        self._traces.clear()
        self._fft_pane = None
        self._fft_trace = None
        self._math_pane = None
        self._math_trace = None

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

            # Link X axes
            if prev_pane is not None:
                pane.setXLink(prev_pane)
            prev_pane = pane

            self._update_pane_range(ch)
            row += 1

        # Re-add math pane if it was enabled before rebuild
        if self._math_requested:
            self.add_math_pane()

        # Re-add FFT pane if it was enabled before rebuild
        if self._fft_requested:
            self.add_fft_pane()

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
        """Update Y range for a channel pane (or math pane for MATH_CH)."""
        pane = self._panes.get(ch)
        if pane is None and ch == MATH_CH:
            pane = self._math_pane
        if pane is None:
            return
        vdiv = self._vdivs.get(ch, 1.0)
        probe = self._probes.get(ch, 1.0)
        offset = self._offsets.get(ch, 0.0)
        n_divs = 4  # ±4 divisions per pane
        half_range = vdiv * probe * n_divs
        center = offset * probe
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

    def set_channel_offset(self, ch: int, offset: float):
        self._offsets[ch] = offset
        self._update_pane_range(ch)

    def set_channel_probe(self, ch: int, factor: float):
        self._probes[ch] = factor
        self._update_pane_range(ch)

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

    def set_scales(self, v_per_div: float, t_per_div: float):
        self._v_per_div = v_per_div
        self._t_per_div = t_per_div
        for ch in self._panes:
            self._update_pane_range(ch)

    def set_h_position(self, pos: float):
        self._h_position = pos
        for ch in self._panes:
            self._update_pane_range(ch)

    # --- FFT pane ---

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

        # Layout — stacked so we can switch between combined/split
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._waveform)        # index 0
        self._stack.addWidget(self._split.widget)     # index 1
        self._stack.setCurrentIndex(0)

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

    def set_trigger_position(self, time_pos: float):
        self._waveform.set_trigger_position(time_pos)

    def set_trigger_level(self, level: float):
        self._waveform.set_trigger_level(level)

    def set_trigger_slope(self, slope: str):
        self._waveform.set_trigger_slope(slope)

    def set_trigger_source_offset(self, offset: float):
        self._waveform.set_trigger_source_offset(offset)

    def set_cursor_mode(self, mode: str):
        self._waveform.set_cursor_mode(mode)

    def set_time_cursor(self, cursor_id: int, value: float):
        self._waveform.set_time_cursor(cursor_id, value)

    def set_volt_cursor(self, cursor_id: int, value: float):
        self._waveform.set_volt_cursor(cursor_id, value)

    def set_cursor_current_mode(self, active: bool, channel: int | None = None):
        self._waveform.set_cursor_current_mode(active, channel)

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

    # --- FFT (split-mode only — needs independent frequency X-axis) ---

    def update_fft(self, freq: np.ndarray, magnitude: np.ndarray, scale: str = "dbv"):
        self._split.update_fft(freq, magnitude, scale)

    def add_fft_pane(self):
        self._split.add_fft_pane()
        if self._mode == "split":
            self._split.rebuild()

    def remove_fft_pane(self):
        self._split.remove_fft_pane()
        if self._mode == "split":
            self._split.rebuild()

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
