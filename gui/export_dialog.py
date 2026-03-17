"""
Export dialog — unified export for waveform data (CSV/JSON) and graph (PNG/PDF).

Two tabs:
  Data  — export raw waveform values as CSV or JSON
  Graph — export rendered graph image as PNG or PDF (with light mode option)
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QMarginsF, QPoint
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QPageLayout, QPageSize,
    QPdfWriter, QPolygon,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QCheckBox, QSpinBox, QLabel, QPushButton, QFileDialog,
    QTabWidget, QWidget, QButtonGroup, QFrame,
)

from gui.theme import (
    format_si, format_voltage, format_time, format_frequency, format_percent,
    format_current, format_adiv,
)
from processing.waveform import WaveformData


# ---------------------------------------------------------------------------
# Data classes for export settings
# ---------------------------------------------------------------------------

@dataclass
class DataExportSettings:
    format: str      # "csv" or "json"
    path: str


@dataclass
class GraphExportSettings:
    format: str          # "png" or "pdf"
    light_mode: bool
    show_measurements: bool
    show_cursors: bool
    show_trigger: bool
    show_scale_labels: bool
    show_gnd_markers: bool
    split_view: bool
    width: int
    height: int
    path: str


# ---------------------------------------------------------------------------
# Color palettes for graph rendering
# ---------------------------------------------------------------------------

_DARK_PALETTE = {
    "background": "#0a0a0a",
    "grid": "#333333",
    "grid_center": "#444444",
    "text": "#e0e0e0",
    "text_dim": "#888888",
    "trigger": "#FF4444",
    "cursor": "#FF8800",
}

_LIGHT_PALETTE = {
    "background": "#FFFFFF",
    "grid": "#CCCCCC",
    "grid_center": "#AAAAAA",
    "text": "#222222",
    "text_dim": "#666666",
    "trigger": "#CC0000",
    "cursor": "#CC6600",
}


# ---------------------------------------------------------------------------
# Export dialog
# ---------------------------------------------------------------------------

class ExportDialog(QDialog):
    """Unified export dialog with Data and Graph tabs."""

    def __init__(self, has_data: bool = True, cursor_mode: str = "off",
                 split_view: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._has_data = has_data
        self._cursor_mode = cursor_mode
        self._split_view = split_view
        self._result_data: DataExportSettings | None = None
        self._result_graph: GraphExportSettings | None = None

        layout = QVBoxLayout(self)

        # --- Tab widget ---
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._build_data_tab()
        self._build_graph_tab()

    # ----- Data tab -----

    def _build_data_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Format
        fmt_group = QGroupBox("Format")
        fmt_layout = QHBoxLayout(fmt_group)
        self._data_fmt_group = QButtonGroup(self)
        self._data_csv_radio = QRadioButton("CSV")
        self._data_json_radio = QRadioButton("JSON")
        self._data_npz_radio = QRadioButton("NPZ")
        self._data_csv_radio.setChecked(True)
        self._data_fmt_group.addButton(self._data_csv_radio)
        self._data_fmt_group.addButton(self._data_json_radio)
        self._data_fmt_group.addButton(self._data_npz_radio)
        fmt_layout.addWidget(self._data_csv_radio)
        fmt_layout.addWidget(self._data_json_radio)
        fmt_layout.addWidget(self._data_npz_radio)
        fmt_layout.addStretch()
        layout.addWidget(fmt_group)

        # Info label
        info = QLabel(
            "Exports time + voltage data for all enabled channels.\n"
            "CSV/JSON: probe-adjusted voltage with metadata.\n"
            "NPZ: raw scope-space voltage (NumPy, lossless)."
        )
        info.setStyleSheet("color: #888888; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()

        # Export button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        export_btn = QPushButton("Export…")
        export_btn.setFixedWidth(120)
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(
            "QPushButton { background-color: #4a9eff; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #5ab0ff; }"
        )
        export_btn.clicked.connect(self._on_data_export)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)

        self._tabs.addTab(tab, "Data")

    # ----- Graph tab -----

    def _build_graph_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Format
        fmt_group = QGroupBox("Format")
        fmt_layout = QHBoxLayout(fmt_group)
        self._graph_fmt_group = QButtonGroup(self)
        self._graph_png_radio = QRadioButton("PNG")
        self._graph_pdf_radio = QRadioButton("PDF")
        self._graph_png_radio.setChecked(True)
        self._graph_fmt_group.addButton(self._graph_png_radio)
        self._graph_fmt_group.addButton(self._graph_pdf_radio)
        fmt_layout.addWidget(self._graph_png_radio)
        fmt_layout.addWidget(self._graph_pdf_radio)
        fmt_layout.addStretch()
        layout.addWidget(fmt_group)

        # Theme
        theme_group = QGroupBox("Theme")
        theme_layout = QHBoxLayout(theme_group)
        self._theme_group = QButtonGroup(self)
        self._dark_radio = QRadioButton("Dark")
        self._light_radio = QRadioButton("Light (printing)")
        self._dark_radio.setChecked(True)
        self._theme_group.addButton(self._dark_radio)
        self._theme_group.addButton(self._light_radio)
        theme_layout.addWidget(self._dark_radio)
        theme_layout.addWidget(self._light_radio)
        theme_layout.addStretch()
        layout.addWidget(theme_group)

        # Include checkboxes
        include_group = QGroupBox("Include")
        include_layout = QVBoxLayout(include_group)
        self._cb_measurements = QCheckBox("Measurements table")
        self._cb_cursors = QCheckBox("Cursors")
        self._cb_trigger = QCheckBox("Trigger level")
        self._cb_scale_labels = QCheckBox("V/div && T/div labels")
        self._cb_gnd_markers = QCheckBox("GND markers")
        self._cb_split_view = QCheckBox("Split channels (separate graphs)")
        for cb in [self._cb_measurements, self._cb_cursors, self._cb_trigger,
                    self._cb_scale_labels, self._cb_gnd_markers, self._cb_split_view]:
            cb.setChecked(True)
            include_layout.addWidget(cb)
        self._cb_split_view.setChecked(self._split_view)
        # Disable cursors checkbox if no cursors active
        if self._cursor_mode == "off":
            self._cb_cursors.setChecked(False)
            self._cb_cursors.setEnabled(False)
        layout.addWidget(include_group)

        # Resolution (PNG only)
        res_group = QGroupBox("Resolution")
        res_layout = QHBoxLayout(res_group)
        self._width_spin = QSpinBox()
        self._width_spin.setRange(640, 7680)
        self._width_spin.setValue(1920)
        self._width_spin.setSuffix(" px")
        self._height_spin = QSpinBox()
        self._height_spin.setRange(480, 4320)
        self._height_spin.setValue(1080)
        self._height_spin.setSuffix(" px")
        res_layout.addWidget(self._width_spin)
        res_layout.addWidget(QLabel("×"))
        res_layout.addWidget(self._height_spin)
        res_layout.addStretch()
        layout.addWidget(res_group)
        self._res_group = res_group

        # Disable resolution for PDF
        self._graph_pdf_radio.toggled.connect(
            lambda pdf: self._res_group.setEnabled(not pdf)
        )

        # Export button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        export_btn = QPushButton("Export…")
        export_btn.setFixedWidth(120)
        export_btn.setFixedHeight(36)
        export_btn.setStyleSheet(
            "QPushButton { background-color: #4a9eff; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #5ab0ff; }"
        )
        export_btn.clicked.connect(self._on_graph_export)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)

        self._tabs.addTab(tab, "Graph")

    # ----- Handlers -----

    def _on_data_export(self):
        if self._data_npz_radio.isChecked():
            fmt, ext = "npz", "npz"
        elif self._data_json_radio.isChecked():
            fmt, ext = "json", "json"
        else:
            fmt, ext = "csv", "csv"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"waveform_{ts}.{ext}"
        filter_map = {
            "csv": "CSV Files (*.csv)",
            "json": "JSON Files (*.json)",
            "npz": "NumPy Archives (*.npz)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()}", default_name, filter_map[fmt]
        )
        if not path:
            return
        self._result_data = DataExportSettings(format=fmt, path=path)
        self.accept()

    def _on_graph_export(self):
        fmt = "png" if self._graph_png_radio.isChecked() else "pdf"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"graph_{ts}.{fmt}"
        filter_str = (
            "PNG Images (*.png)" if fmt == "png"
            else "PDF Documents (*.pdf)"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()}", default_name, filter_str
        )
        if not path:
            return

        w = self._width_spin.value() if fmt == "png" else 1920
        h = self._height_spin.value() if fmt == "png" else 1080

        self._result_graph = GraphExportSettings(
            format=fmt,
            light_mode=self._light_radio.isChecked(),
            show_measurements=self._cb_measurements.isChecked(),
            show_cursors=self._cb_cursors.isChecked(),
            show_trigger=self._cb_trigger.isChecked(),
            show_scale_labels=self._cb_scale_labels.isChecked(),
            show_gnd_markers=self._cb_gnd_markers.isChecked(),
            split_view=self._cb_split_view.isChecked(),
            width=w,
            height=h,
            path=path,
        )
        self.accept()

    # ----- Results -----

    @property
    def data_settings(self) -> DataExportSettings | None:
        return self._result_data

    @property
    def graph_settings(self) -> GraphExportSettings | None:
        return self._result_graph


# ---------------------------------------------------------------------------
# Graph renderer — QPainter on QImage
# ---------------------------------------------------------------------------

NUM_H_DIVS = 10
NUM_V_DIVS = 8

# Margins (fraction of total image size)
_MARGIN_LEFT = 0.08
_MARGIN_RIGHT = 0.04
_MARGIN_TOP = 0.06
_MARGIN_BOTTOM_GRAPH = 0.08  # Bottom of graph area
_MEAS_TABLE_HEIGHT = 0.12    # Additional space for measurement table


def render_graph(
    waveforms: dict[int, WaveformData],
    measurements: dict[int, dict],
    colors: dict[int, str],
    trigger: dict,
    cursors: dict,
    channel_settings: dict,
    settings: GraphExportSettings,
    enabled_measurements: list[str] | None = None,
) -> QImage:
    """Render an oscilloscope graph to a QImage.

    Args:
        waveforms: Dict of channel → WaveformData.
        measurements: Dict of channel → measurement dict.
        colors: Dict of channel → color hex string.
        trigger: {"level": float, "source": str, "slope": str}.
        cursors: {"mode": str, "time": [t1, t2], "volt": [v1, v2], "channel": int}.
        channel_settings: Dict of channel → {"v_per_div", "offset", "probe_factor"}.
        settings: GraphExportSettings with rendering options.
        enabled_measurements: List of enabled measurement display names
            (e.g. ["Vpp", "Freq", "Rise"]). If None, all are shown.

    Returns:
        QImage with the rendered graph.
    """
    pal = _LIGHT_PALETTE if settings.light_mode else _DARK_PALETTE

    total_w = settings.width
    # Add space below graph for measurement table if requested
    has_meas = settings.show_measurements and measurements
    total_h = settings.height
    if has_meas:
        total_h = int(settings.height / (1.0 - _MEAS_TABLE_HEIGHT))

    img = QImage(total_w, total_h, QImage.Format.Format_ARGB32)
    img.fill(QColor(pal["background"]))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Graph area rectangle
    gx = int(total_w * _MARGIN_LEFT)
    gy = int(total_h * _MARGIN_TOP)
    gw = int(total_w * (1.0 - _MARGIN_LEFT - _MARGIN_RIGHT))
    gh = int(settings.height * (1.0 - _MARGIN_TOP - _MARGIN_BOTTOM_GRAPH))

    # --- Determine axis ranges ---
    # Use first channel's waveform to establish T/div
    channels = sorted(waveforms.keys())
    if not channels:
        p.end()
        return img

    ref_wf = waveforms[channels[0]]
    t_per_div = ref_wf.t_per_div
    # Use active channel's V/div for the display axis
    active_ch = channels[0]
    active_settings = channel_settings.get(active_ch, {})
    v_per_div = active_settings.get("v_per_div", 1.0)
    probe = active_settings.get("probe_factor", 1.0)
    display_vdiv = v_per_div * probe

    t_half = (NUM_H_DIVS / 2) * t_per_div
    v_half = (NUM_V_DIVS / 2) * display_vdiv

    def time_to_x(t):
        return gx + (t + t_half) / (2 * t_half) * gw

    def volt_to_y(v):
        return gy + gh - (v + v_half) / (2 * v_half) * gh

    # --- Title ---
    title_font = QFont("Menlo", max(10, total_w // 120))
    title_font.setBold(True)
    p.setFont(title_font)
    p.setPen(QColor(pal["text"]))
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p.drawText(gx, gy - 8, f"Agilent U2702A — {ts}")

    # --- Grid ---
    grid_pen = QPen(QColor(pal["grid"]), 1.0, Qt.PenStyle.DashLine)
    center_pen = QPen(QColor(pal["grid_center"]), 1.5, Qt.PenStyle.SolidLine)

    # Vertical grid lines
    for i in range(-NUM_H_DIVS // 2, NUM_H_DIVS // 2 + 1):
        x = time_to_x(i * t_per_div)
        p.setPen(center_pen if i == 0 else grid_pen)
        p.drawLine(int(x), gy, int(x), gy + gh)

    # Horizontal grid lines
    for i in range(-NUM_V_DIVS // 2, NUM_V_DIVS // 2 + 1):
        y = volt_to_y(i * display_vdiv)
        p.setPen(center_pen if i == 0 else grid_pen)
        p.drawLine(gx, int(y), gx + gw, int(y))

    # --- Graph border ---
    border_pen = QPen(QColor(pal["grid_center"]), 1.0)
    p.setPen(border_pen)
    p.drawRect(gx, gy, gw, gh)

    # --- Scale label: T/div below graph center ---
    if settings.show_scale_labels:
        label_font = QFont("Menlo", max(9, total_w // 160))
        p.setFont(label_font)
        fm = p.fontMetrics()
        y_label = gy + gh + fm.height() + 4

        # T/div label (bottom center)
        p.setPen(QColor(pal["text_dim"]))
        tdiv_str = format_si(t_per_div, "s/div")
        tw = fm.horizontalAdvance(tdiv_str)
        p.drawText(gx + gw // 2 - tw // 2, y_label, tdiv_str)

    # --- Waveform traces (clipped to graph area) ---
    if settings.split_view and len(channels) > 1:
        # Split view: each channel gets its own vertical slice
        n_panes = len(channels)
        pane_gap = 4
        pane_h = (gh - pane_gap * (n_panes - 1)) // n_panes
        for pane_idx, ch in enumerate(channels):
            pane_y = gy + pane_idx * (pane_h + pane_gap)
            ch_s = channel_settings.get(ch, {})
            ch_vdiv = ch_s.get("v_per_div", 1.0)
            ch_probe = ch_s.get("probe_factor", 1.0)
            ch_effective = ch_vdiv * ch_probe
            ch_offset = ch_s.get("offset", 0.0)
            pane_v_half = (NUM_V_DIVS / 2) * ch_effective

            def _pane_volt_to_y(v, _py=pane_y, _ph=pane_h, _vh=pane_v_half):
                return _py + _ph - (v + _vh) / (2 * _vh) * _ph

            # Pane border
            p.setPen(QPen(QColor(pal["grid_center"]), 0.5))
            p.drawRect(gx, pane_y, gw, pane_h)

            # Pane grid
            grid_pen_split = QPen(QColor(pal["grid"]), 0.5, Qt.PenStyle.DotLine)
            for gi in range(-NUM_V_DIVS // 2, NUM_V_DIVS // 2 + 1):
                y_line = _pane_volt_to_y(gi * ch_effective)
                p.setPen(grid_pen_split)
                p.drawLine(gx, int(y_line), gx + gw, int(y_line))

            # Channel label
            label_font = QFont("Menlo", max(8, total_w // 180))
            label_font.setBold(True)
            p.setFont(label_font)
            color = colors.get(ch, "#FFFFFF")
            p.setPen(QColor(color))
            p.drawText(gx + 4, pane_y + 14, f"CH{ch}")

            # Trace
            p.save()
            p.setClipRect(gx, pane_y, gw, pane_h)
            wf = waveforms[ch]
            trace_pen = QPen(QColor(color), 1.5)
            p.setPen(trace_pen)
            t = wf.time_axis
            v = wf.voltage * ch_probe
            n = len(t)
            if n >= 2:
                prev_x = time_to_x(t[0])
                prev_y = _pane_volt_to_y(v[0])
                for i in range(1, n):
                    curr_x = time_to_x(t[i])
                    curr_y = _pane_volt_to_y(v[i])
                    p.drawLine(int(prev_x), int(prev_y), int(curr_x), int(curr_y))
                    prev_x = curr_x
                    prev_y = curr_y
            p.restore()

            # V/div label for this pane
            if settings.show_scale_labels:
                scale_font = QFont("Menlo", max(7, total_w // 200))
                p.setFont(scale_font)
                p.setPen(QColor(pal["text_dim"]))
                vdiv_str = format_si(ch_effective, "V/div")
                p.drawText(gx + gw - p.fontMetrics().horizontalAdvance(vdiv_str) - 4,
                           pane_y + pane_h - 4, vdiv_str)
    else:
        # Combined view: all channels overlaid
        p.save()
        p.setClipRect(gx, gy, gw, gh)
        for ch in channels:
            wf = waveforms[ch]
            color = colors.get(ch, "#FFFFFF")
            trace_pen = QPen(QColor(color), 1.5)
            p.setPen(trace_pen)

            ch_settings_ch = channel_settings.get(ch, {})
            ch_vdiv = ch_settings_ch.get("v_per_div", 1.0)
            ch_probe = ch_settings_ch.get("probe_factor", 1.0)
            ch_effective = ch_vdiv * ch_probe
            if ch_effective > 0:
                scale = (display_vdiv / ch_effective) * ch_probe
            else:
                scale = 1.0

            t = wf.time_axis
            v = wf.voltage * scale

            n = len(t)
            if n < 2:
                continue
            prev_x = time_to_x(t[0])
            prev_y = volt_to_y(v[0])
            for i in range(1, n):
                curr_x = time_to_x(t[i])
                curr_y = volt_to_y(v[i])
                p.drawLine(int(prev_x), int(prev_y), int(curr_x), int(curr_y))
                prev_x = curr_x
                prev_y = curr_y
        p.restore()

    # --- Trigger crossing point on waveform ---
    if settings.show_trigger and trigger:
        trig_source = trigger.get("source", "CHAN1")
        if trig_source.startswith("CHAN"):
            src_ch = int(trig_source[4:])
            if src_ch in waveforms:
                trig_level = trigger.get("level", 0.0)
                # Scale trigger level to display space
                ch_s = channel_settings.get(src_ch, {})
                src_vdiv = ch_s.get("v_per_div", 1.0)
                src_probe = ch_s.get("probe_factor", 1.0)
                src_effective = src_vdiv * src_probe
                trig_scale = (display_vdiv / src_effective) * src_probe if src_effective > 0 else 1.0
                trig_display = trig_level * trig_scale
                # Draw a filled circle at (time=0, trigger level)
                dot_x = int(time_to_x(0.0))
                dot_y = int(volt_to_y(trig_display))
                dot_r = max(4, total_w // 300)
                p.setBrush(QColor(pal["trigger"]))
                p.setPen(QPen(QColor(pal["background"]), 1.5))
                p.drawEllipse(dot_x - dot_r, dot_y - dot_r,
                              2 * dot_r, 2 * dot_r)
                p.setBrush(Qt.BrushStyle.NoBrush)

    # --- GND markers ---
    if settings.show_gnd_markers:
        marker_font = QFont("Menlo", max(9, total_w // 160))
        marker_font.setBold(True)
        p.setFont(marker_font)
        for ch in channels:
            color = colors.get(ch, "#FFFFFF")
            ch_settings = channel_settings.get(ch, {})
            offset = ch_settings.get("offset", 0.0)
            ch_vdiv = ch_settings.get("v_per_div", 1.0)
            ch_probe = ch_settings.get("probe_factor", 1.0)
            ch_effective = ch_vdiv * ch_probe
            if ch_effective > 0:
                scale = (display_vdiv / ch_effective) * ch_probe
            else:
                scale = 1.0

            # GND marker Y position = offset scaled to display space
            gnd_y = volt_to_y(offset * scale)

            # Draw badge
            badge_text = f"{ch} ▶"
            if ch_probe != 1.0:
                badge_text += f" {ch_probe:g}x"
            p.setPen(QColor(color))
            fm = p.fontMetrics()
            p.drawText(gx - fm.horizontalAdvance(badge_text) - 6,
                       int(gnd_y) + fm.ascent() // 2, badge_text)

    # --- Trigger level + trigger position marker ---
    if settings.show_trigger and trigger:
        trig_level = trigger.get("level", 0.0)
        trig_source = trigger.get("source", "CHAN1")
        # Scale trigger level to display space using source channel's scale
        if trig_source.startswith("CHAN"):
            src_ch = int(trig_source[4:])
            ch_s = channel_settings.get(src_ch, {})
            src_vdiv = ch_s.get("v_per_div", 1.0)
            src_probe = ch_s.get("probe_factor", 1.0)
            src_effective = src_vdiv * src_probe
            src_offset = ch_s.get("offset", 0.0)
            if src_effective > 0:
                trig_scale = (display_vdiv / src_effective) * src_probe
            else:
                trig_scale = 1.0
            # The trigger level is in scope-space relative to the source channel
            trig_display = trig_level * trig_scale
        else:
            trig_display = trig_level

        trig_pen = QPen(QColor(pal["trigger"]), 1.0, Qt.PenStyle.DashLine)
        p.setPen(trig_pen)
        ty = volt_to_y(trig_display)
        p.drawLine(gx, int(ty), gx + gw, int(ty))

        # Trigger badge on right edge
        badge_font = QFont("Menlo", max(8, total_w // 180))
        badge_font.setBold(True)
        p.setFont(badge_font)
        trig_text = f"T {format_voltage(trig_level)}"
        fm = p.fontMetrics()
        p.setPen(QColor(pal["trigger"]))
        p.drawText(gx + gw + 4, int(ty) + fm.ascent() // 2, trig_text)

        # Trigger position ▼ marker on top edge at time=0
        trig_x = int(time_to_x(0.0))
        tri_size = max(6, total_w // 200)
        p.setBrush(QColor(pal["trigger"]))
        p.setPen(Qt.PenStyle.NoPen)
        triangle = QPolygon([
            QPoint(trig_x, gy),
            QPoint(trig_x - tri_size, gy - tri_size - 2),
            QPoint(trig_x + tri_size, gy - tri_size - 2),
        ])
        p.drawPolygon(triangle)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # --- Cursors ---
    if settings.show_cursors and cursors:
        cursor_mode = cursors.get("mode", "off")
        if cursor_mode != "off":
            cursor_pen = QPen(QColor(pal["cursor"]), 1.5, Qt.PenStyle.DashDotLine)
            cursor_font = QFont("Menlo", max(8, total_w // 180))
            cursor_font.setBold(True)
            p.setFont(cursor_font)
            fm = p.fontMetrics()

            time_vals = cursors.get("time", [0.0, 0.0])
            # Display-space values for positioning lines on graph
            volt_display = cursors.get("volt_display",
                                       cursors.get("volt", [0.0, 0.0]))
            # Physical values for labels (probe-scaled, current-converted)
            volt_physical = cursors.get("volt_physical", volt_display)
            cursor_ch = cursors.get("channel", 1)
            t_names = ["C-X1", "C-X2"]   # time cursors
            v_names = ["C-Y1", "C-Y2"]   # voltage cursors

            # Determine if cursor channel is in current mode
            ch_s = channel_settings.get(cursor_ch, {})
            is_current = ch_s.get("current_mode", False)
            fmt_v = format_current if is_current else format_voltage

            # Time cursor lines with T1/T2 labels
            if cursor_mode in ("time", "both"):
                for i, t_val in enumerate(time_vals):
                    cx = time_to_x(t_val)
                    p.setPen(cursor_pen)
                    p.drawLine(int(cx), gy, int(cx), gy + gh)
                    # Label: "T1: -500 µs"
                    p.setPen(QColor(pal["cursor"]))
                    label = f"{t_names[i]}: {format_time(t_val)}"
                    p.drawText(int(cx) + 4, gy + 14 + i * (fm.height() + 2),
                               label)

            # Voltage cursor lines with V1/V2 labels (physical values)
            if cursor_mode in ("voltage", "both"):
                for i in range(2):
                    cy = volt_to_y(volt_display[i])
                    p.setPen(cursor_pen)
                    p.drawLine(gx, int(cy), gx + gw, int(cy))
                    # Label uses physical value
                    p.setPen(QColor(pal["cursor"]))
                    label = f"{v_names[i]}: {fmt_v(volt_physical[i])}"
                    p.drawText(gx + gw - fm.horizontalAdvance(label) - 4,
                               int(cy) - 4 - i * (fm.height() + 2), label)

            # --- Cursor readout bar (horizontal, like the GUI) ---
            readout_font = QFont("Menlo", max(9, total_w // 160))
            readout_font.setBold(True)
            p.setFont(readout_font)
            fm = p.fontMetrics()
            bar_y = gy + gh - fm.height() - 8  # Bottom of graph
            bar_x = gx + 10

            bar_parts = []
            if cursor_mode in ("time", "both"):
                t1, t2 = time_vals
                dt = abs(t2 - t1)
                inv_dt = format_frequency(1.0 / dt) if dt > 1e-15 else "---"
                bar_parts.append(("label", "C-X1:"))
                bar_parts.append(("value", format_time(t1)))
                bar_parts.append(("label", "C-X2:"))
                bar_parts.append(("value", format_time(t2)))
                bar_parts.append(("label", "ΔT:"))
                bar_parts.append(("value", format_time(dt)))
                bar_parts.append(("label", "1/ΔT:"))
                bar_parts.append(("value", inv_dt))

            if cursor_mode == "both":
                bar_parts.append(("sep", "│"))

            if cursor_mode in ("voltage", "both"):
                ch_color = colors.get(cursor_ch, pal["cursor"])
                bar_parts.append(("channel", f"CH{cursor_ch}"))
                bar_parts.append(("label", "C-Y1:"))
                bar_parts.append(("value", fmt_v(volt_physical[0])))
                bar_parts.append(("label", "C-Y2:"))
                bar_parts.append(("value", fmt_v(volt_physical[1])))
                dv = abs(volt_physical[1] - volt_physical[0])
                v_label = "ΔI:" if is_current else "ΔV:"
                bar_parts.append(("label", v_label))
                bar_parts.append(("value", fmt_v(dv)))

            # Draw background bar
            total_text_w = sum(
                fm.horizontalAdvance(text) + (6 if kind != "sep" else 12)
                for kind, text in bar_parts
            )
            bg_color = QColor(pal["background"])
            bg_color.setAlpha(200)
            p.fillRect(bar_x - 6, bar_y - 2,
                       total_text_w + 12, fm.height() + 4, bg_color)

            # Draw parts
            cx_pos = bar_x
            for kind, text in bar_parts:
                if kind == "label":
                    p.setPen(QColor(pal["cursor"]))
                elif kind == "value":
                    p.setPen(QColor(pal["text"]))
                elif kind == "sep":
                    p.setPen(QColor(pal["text_dim"]))
                elif kind == "channel":
                    p.setPen(QColor(ch_color))
                p.drawText(cx_pos, bar_y + fm.ascent(), text)
                cx_pos += fm.horizontalAdvance(text) + (
                    12 if kind == "sep" else 6)

    # --- Measurement table below graph ---
    if has_meas:
        _render_measurement_table(p, measurements, colors, channels,
                                  gx, gy + gh + 30, gw, total_h - (gy + gh + 30),
                                  pal, enabled_measurements,
                                  channel_settings=channel_settings)

    p.end()
    return img


def _render_measurement_table(
    p: QPainter,
    measurements: dict[int, dict],
    colors: dict[int, str],
    channels: list[int],
    x: int, y: int, w: int, h: int,
    pal: dict,
    enabled_measurements: list[str] | None = None,
    channel_settings: dict | None = None,
):
    """Render measurement values in a table below the graph.

    The channel label column shows V/div (with probe) so that the scale
    info lives alongside the measurement data instead of as a separate row.
    Current-mode channels use A/A-div units instead of V/V-div.
    """
    _VOLTAGE_MEAS_COLS = [
        ("Vpp", "vpp", format_voltage),
        ("Vmin", "vmin", format_voltage),
        ("Vmax", "vmax", format_voltage),
        ("Vrms", "vrms", format_voltage),
        ("Vmean", "vmean", format_voltage),
    ]
    _CURRENT_MEAS_COLS = [
        ("Ipp", "vpp", format_current),
        ("Imin", "vmin", format_current),
        ("Imax", "vmax", format_current),
        ("Irms", "vrms", format_current),
        ("Imean", "vmean", format_current),
    ]
    _TIME_MEAS_COLS = [
        ("Freq", "frequency", format_frequency),
        ("Period", "period", format_time),
        ("Rise", "rise_time", format_time),
        ("Fall", "fall_time", format_time),
        ("Duty", "duty_cycle", format_percent),
    ]
    # Map display names: "Vpp" ↔ "Ipp" etc. for enabled filtering
    _V_TO_I_NAME = {"Vpp": "Ipp", "Vmin": "Imin", "Vmax": "Imax",
                    "Vrms": "Irms", "Vmean": "Imean"}

    # Check if ANY channel is in current mode
    any_current = False
    if channel_settings:
        any_current = any(
            channel_settings.get(ch, {}).get("current_mode", False)
            for ch in channels
        )

    # Build column list — use voltage or current header names
    # For mixed mode (some V, some A), use voltage headers (majority case)
    all_cols = (_CURRENT_MEAS_COLS if any_current else _VOLTAGE_MEAS_COLS) \
        + _TIME_MEAS_COLS

    # Filter to only enabled measurements (if specified)
    if enabled_measurements is not None:
        enabled_set = set(enabled_measurements)
        # Also match I↔V equivalents
        expanded = set(enabled_set)
        for v_name, i_name in _V_TO_I_NAME.items():
            if v_name in enabled_set:
                expanded.add(i_name)
            if i_name in enabled_set:
                expanded.add(v_name)
        meas_cols = [(d, k, f) for d, k, f in all_cols if d in expanded]
    else:
        meas_cols = all_cols

    if not meas_cols:
        return

    font = QFont("Menlo", max(9, w // 140))
    p.setFont(font)
    fm = p.fontMetrics()
    row_h = fm.height() + 6

    # Calculate first column width to fit longest channel label
    font_bold = QFont(font)
    font_bold.setBold(True)
    p.setFont(font_bold)
    fm_bold = p.fontMetrics()
    label_w = 0
    for ch in channels:
        ch_label = _make_ch_label(ch, channel_settings)
        lw = fm_bold.horizontalAdvance(ch_label)
        if lw > label_w:
            label_w = lw
    label_w += 16  # padding after label
    p.setFont(font)
    fm = p.fontMetrics()

    # Remaining width shared equally by measurement columns
    data_w = w - label_w
    col_w = max(data_w // len(meas_cols), 60)

    # Header row
    p.setPen(QColor(pal["text_dim"]))
    for ci, (label, _, _) in enumerate(meas_cols):
        p.drawText(x + label_w + ci * col_w, y + fm.ascent(), label)

    # Separator line
    sep_y = y + row_h - 2
    p.setPen(QPen(QColor(pal["grid"]), 1.0))
    p.drawLine(x, sep_y, x + w, sep_y)

    # Channel rows
    for ri, ch in enumerate(channels):
        meas = measurements.get(ch, {})
        row_y = y + (ri + 1) * row_h + fm.ascent()
        color = colors.get(ch, "#FFFFFF")
        is_current = (channel_settings or {}).get(ch, {}).get(
            "current_mode", False)

        # Channel label with V/div or A/div
        p.setPen(QColor(color))
        p.setFont(font_bold)
        ch_label = _make_ch_label(ch, channel_settings)
        p.drawText(x, row_y, ch_label)
        p.setFont(font)

        # Values — use format_current for voltage-type measurements when
        # this channel is in current mode
        for ci, (_, key, fmt_func) in enumerate(meas_cols):
            val = meas.get(key)
            if val is not None:
                p.setPen(QColor(color))
                # Override format for voltage-type measurements in current mode
                if is_current and fmt_func is format_voltage:
                    p.drawText(x + label_w + ci * col_w, row_y,
                               format_current(val))
                elif not is_current and fmt_func is format_current:
                    p.drawText(x + label_w + ci * col_w, row_y,
                               format_voltage(val))
                else:
                    p.drawText(x + label_w + ci * col_w, row_y,
                               fmt_func(val))
            else:
                p.setPen(QColor(pal["text_dim"]))
                p.drawText(x + label_w + ci * col_w, row_y, "---")


def _make_ch_label(ch: int, channel_settings: dict | None) -> str:
    """Build channel label string with V/div or A/div and probe tag."""
    if not channel_settings:
        return f"CH{ch}"
    ch_s = channel_settings.get(ch, {})
    ch_vdiv = ch_s.get("v_per_div", 1.0)
    ch_probe = ch_s.get("probe_factor", 1.0)
    is_current = ch_s.get("current_mode", False)
    effective = ch_vdiv * ch_probe
    probe_tag = f" ({ch_probe:g}x)" if ch_probe != 1.0 else ""
    unit = "A/div" if is_current else "V/div"
    return f"CH{ch}{probe_tag}  {format_si(effective, unit)}"


def save_graph(img: QImage, settings: GraphExportSettings):
    """Save a rendered graph to disk as PNG or PDF.

    Args:
        img: Rendered QImage from render_graph().
        settings: Export settings including path and format.
    """
    path = Path(settings.path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if settings.format == "png":
        img.save(str(path), "PNG")
    elif settings.format == "pdf":
        page_layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Landscape,
            QMarginsF(10, 10, 10, 10),
        )
        writer = QPdfWriter(str(path))
        writer.setPageLayout(page_layout)
        # Scale image to fill the PDF page
        painter = QPainter(writer)
        page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
        painter.drawImage(page_rect, img)
        painter.end()
