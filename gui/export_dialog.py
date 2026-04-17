"""
Export dialog — unified export for waveform data (CSV/JSON) and graph (PNG/PDF).

Two tabs:
  Data  — export raw waveform values as CSV or JSON
  Graph — export rendered graph image as PNG or PDF (with light mode option)

Graph rendering itself lives in ``gui/graph_renderer.py``; this file is
just the dialog UI. ``render_graph``, ``save_graph``, and
``GraphExportSettings`` are re-exported here for backwards compatibility.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QCheckBox, QSpinBox, QLabel, QPushButton, QFileDialog,
    QTabWidget, QWidget, QButtonGroup, QFrame,
)

# Re-exports: callers historically import these from gui.export_dialog.
from gui.graph_renderer import (  # noqa: F401  (public re-export)
    render_graph, save_graph, GraphExportSettings,
)


# ---------------------------------------------------------------------------
# Data classes for export settings
# ---------------------------------------------------------------------------

@dataclass
class DataExportSettings:
    format: str      # "csv" or "json"
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


