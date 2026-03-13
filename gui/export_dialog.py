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
from PySide6.QtCore import Qt, QMarginsF
from PySide6.QtGui import (
    QColor, QFont, QImage, QPainter, QPen, QPageLayout, QPageSize,
    QPdfWriter,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QCheckBox, QSpinBox, QLabel, QPushButton, QFileDialog,
    QTabWidget, QWidget, QButtonGroup, QFrame,
)

from gui.theme import format_si, format_voltage, format_time, format_frequency
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
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._has_data = has_data
        self._cursor_mode = cursor_mode
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
        self._data_csv_radio.setChecked(True)
        self._data_fmt_group.addButton(self._data_csv_radio)
        self._data_fmt_group.addButton(self._data_json_radio)
        fmt_layout.addWidget(self._data_csv_radio)
        fmt_layout.addWidget(self._data_json_radio)
        fmt_layout.addStretch()
        layout.addWidget(fmt_group)

        # Info label
        info = QLabel(
            "Exports time + voltage data for all enabled channels.\n"
            "Includes metadata header with scope settings and measurements."
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
        for cb in [self._cb_measurements, self._cb_cursors, self._cb_trigger,
                    self._cb_scale_labels, self._cb_gnd_markers]:
            cb.setChecked(True)
            include_layout.addWidget(cb)
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
        fmt = "csv" if self._data_csv_radio.isChecked() else "json"
        ext = "csv" if fmt == "csv" else "json"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"waveform_{ts}.{ext}"
        filter_str = (
            "CSV Files (*.csv)" if fmt == "csv"
            else "JSON Files (*.json)"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()}", default_name, filter_str
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

    # --- Scale labels ---
    if settings.show_scale_labels:
        label_font = QFont("Menlo", max(9, total_w // 160))
        p.setFont(label_font)
        p.setPen(QColor(pal["text_dim"]))

        # T/div label (bottom center)
        tdiv_str = format_si(t_per_div, "s/div")
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(tdiv_str)
        p.drawText(gx + gw // 2 - tw // 2, gy + gh + fm.height() + 4, tdiv_str)

        # V/div labels per channel (left side, stacked)
        y_label = gy + gh + fm.height() + 4
        for idx, ch in enumerate(channels):
            ch_settings = channel_settings.get(ch, {})
            ch_vdiv = ch_settings.get("v_per_div", 1.0)
            ch_probe = ch_settings.get("probe_factor", 1.0)
            effective = ch_vdiv * ch_probe
            vdiv_str = f"CH{ch}: {format_si(effective, 'V/div')}"
            color = colors.get(ch, "#FFFFFF")
            p.setPen(QColor(color))
            p.drawText(gx + idx * (total_w // 4), y_label, vdiv_str)

    # --- Waveform traces ---
    for ch in channels:
        wf = waveforms[ch]
        color = colors.get(ch, "#FFFFFF")
        trace_pen = QPen(QColor(color), 1.5)
        p.setPen(trace_pen)

        # Scale voltage to display coordinates (like waveform_widget._voltage_scale)
        ch_settings = channel_settings.get(ch, {})
        ch_vdiv = ch_settings.get("v_per_div", 1.0)
        ch_probe = ch_settings.get("probe_factor", 1.0)
        ch_effective = ch_vdiv * ch_probe
        if ch_effective > 0:
            scale = display_vdiv / ch_effective
        else:
            scale = 1.0

        t = wf.time_axis
        v = wf.voltage * scale

        # Build point path for performance
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
                scale = display_vdiv / ch_effective
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

    # --- Trigger level ---
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
                trig_scale = display_vdiv / src_effective
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

    # --- Cursors ---
    if settings.show_cursors and cursors:
        cursor_mode = cursors.get("mode", "off")
        if cursor_mode != "off":
            cursor_pen = QPen(QColor(pal["cursor"]), 1.5, Qt.PenStyle.DashDotLine)
            cursor_font = QFont("Menlo", max(8, total_w // 180))
            p.setFont(cursor_font)
            fm = p.fontMetrics()

            time_vals = cursors.get("time", [0.0, 0.0])
            volt_vals = cursors.get("volt", [0.0, 0.0])

            if cursor_mode in ("time", "both"):
                p.setPen(cursor_pen)
                for i, t_val in enumerate(time_vals):
                    cx = time_to_x(t_val)
                    p.drawLine(int(cx), gy, int(cx), gy + gh)
                    # Badge
                    p.setPen(QColor(pal["cursor"]))
                    label = format_time(t_val)
                    p.drawText(int(cx) + 4, gy + 14 + i * (fm.height() + 2), label)
                    p.setPen(cursor_pen)

            if cursor_mode in ("voltage", "both"):
                p.setPen(cursor_pen)
                for i, v_val in enumerate(volt_vals):
                    cy = volt_to_y(v_val)
                    p.drawLine(gx, int(cy), gx + gw, int(cy))
                    # Badge
                    p.setPen(QColor(pal["cursor"]))
                    label = format_voltage(v_val)
                    p.drawText(gx + gw - fm.horizontalAdvance(label) - 4,
                               int(cy) - 4 - i * (fm.height() + 2), label)
                    p.setPen(cursor_pen)

    # --- Measurement table below graph ---
    if has_meas:
        _render_measurement_table(p, measurements, colors, channels,
                                  gx, gy + gh + 30, gw, total_h - (gy + gh + 30),
                                  pal)

    p.end()
    return img


def _render_measurement_table(
    p: QPainter,
    measurements: dict[int, dict],
    colors: dict[int, str],
    channels: list[int],
    x: int, y: int, w: int, h: int,
    pal: dict,
):
    """Render measurement values in a table below the graph."""
    _MEAS_COLS = [
        ("Vpp", "vpp", format_voltage),
        ("Vmin", "vmin", format_voltage),
        ("Vmax", "vmax", format_voltage),
        ("Vrms", "vrms", format_voltage),
        ("Freq", "frequency", format_frequency),
        ("Period", "period", format_time),
    ]

    font = QFont("Menlo", max(9, w // 140))
    p.setFont(font)
    fm = p.fontMetrics()
    row_h = fm.height() + 6
    col_w = w // (len(_MEAS_COLS) + 1)  # +1 for channel label column

    # Header row
    p.setPen(QColor(pal["text_dim"]))
    for ci, (label, _, _) in enumerate(_MEAS_COLS):
        p.drawText(x + (ci + 1) * col_w, y + fm.ascent(), label)

    # Separator line
    sep_y = y + row_h - 2
    p.setPen(QPen(QColor(pal["grid"]), 1.0))
    p.drawLine(x, sep_y, x + w, sep_y)

    # Channel rows
    for ri, ch in enumerate(channels):
        meas = measurements.get(ch, {})
        row_y = y + (ri + 1) * row_h + fm.ascent()
        color = colors.get(ch, "#FFFFFF")

        # Channel label
        p.setPen(QColor(color))
        font_bold = QFont(font)
        font_bold.setBold(True)
        p.setFont(font_bold)
        p.drawText(x, row_y, f"CH{ch}")
        p.setFont(font)

        # Values
        for ci, (_, key, fmt_func) in enumerate(_MEAS_COLS):
            val = meas.get(key)
            if val is not None:
                p.setPen(QColor(color))
                p.drawText(x + (ci + 1) * col_w, row_y, fmt_func(val))
            else:
                p.setPen(QColor(pal["text_dim"]))
                p.drawText(x + (ci + 1) * col_w, row_y, "---")


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
