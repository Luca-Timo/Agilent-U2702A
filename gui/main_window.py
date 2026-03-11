"""
Main oscilloscope window — graph left, controls right.

Wires together all components: waveform display, control panels,
acquisition worker, connection dialog, settings, and SCPI tester.
"""

import sys
import os

from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QMenuBar, QStatusBar, QSizePolicy,
    QFrame, QScrollArea, QApplication, QDialog, QTextEdit,
    QDialogButtonBox, QTabWidget,
)
from PySide6.QtGui import QAction, QFont, QShortcut, QKeySequence

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.theme import (
    NUM_CHANNELS, channel_color, format_tdiv, format_vdiv,
    STATUS_GREEN, STATUS_YELLOW, STATUS_RED, ACCENT_BLUE,
    VDIV_VALUES, TDIV_VALUES,
)
from gui.waveform_widget import WaveformWidget
from gui.channel_panel import ChannelPanel
from gui.timebase_panel import TimebasePanel
from gui.trigger_panel import TriggerPanel
from gui.utility_panel import UtilityPanel
from gui.measurement_bar import MeasurementBar
from gui.acquisition_worker import AcquisitionWorker
from gui.connection_dialog import ConnectionDialog
from gui.settings_dialog import SettingsDialog
from processing.waveform import WaveformData
from processing import measurements
from processing.autoscale import pick_vdiv, pick_tdiv, compute_center_offset


class StatusIndicator(QLabel):
    """Colored status indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.set_status("DISCONNECTED")

    def set_status(self, status: str):
        colors = {
            "READY": STATUS_GREEN,
            "CONNECTED": STATUS_GREEN,
            "RUNNING": "#4a9eff",
            "WAITING": STATUS_YELLOW,
            "BOOTING": STATUS_YELLOW,
            "DISCONNECTED": STATUS_RED,
            "STOPPED": STATUS_YELLOW,
        }
        color = colors.get(status, "#888888")
        self.setText(f" {status} ")
        self.setStyleSheet(
            f"background-color: {color}; color: white; "
            f"border-radius: 4px; padding: 2px 8px; "
            f"font-weight: bold; font-size: 11px;"
        )


APP_VERSION = "0.3.0-alpha"
APP_COPYRIGHT = "Copyright © 2026 Luca Bresch"


class AboutDialog(QDialog):
    """About / License dialog — shows app info and GPL v3 license text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About — Agilent U2702A Oscilloscope")
        self.setMinimumSize(560, 420)
        self.resize(600, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Header ---
        header = QLabel(
            f"<h2 style='margin-bottom:2px;'>Agilent U2702A Oscilloscope</h2>"
            f"<p style='color:#888; margin-top:0;'>Version {APP_VERSION}</p>"
        )
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Description
        desc = QLabel(
            "A macOS desktop application for the Agilent U2702A USB oscilloscope,\n"
            "built with PySide6 and PyQtGraph. Uses an ESP32-S3 as a USB bridge\n"
            "to bypass Apple Silicon USB driver limitations."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        layout.addWidget(desc)

        # --- Tabs: About / License ---
        tabs = QTabWidget()

        # About tab
        about_text = QTextEdit()
        about_text.setReadOnly(True)
        about_text.setHtml(
            f"<p><b>{APP_COPYRIGHT}</b></p>"
            "<p>This program is free software: you can redistribute it and/or modify "
            "it under the terms of the GNU General Public License as published by "
            "the Free Software Foundation, either version 3 of the License, or "
            "(at your option) any later version.</p>"
            "<p>This program is distributed in the hope that it will be useful, "
            "but WITHOUT ANY WARRANTY; without even the implied warranty of "
            "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the "
            "GNU General Public License for more details.</p>"
            "<hr>"
            "<p><b>Built with:</b></p>"
            "<ul>"
            "<li>Python 3.11+ / PySide6 (Qt 6)</li>"
            "<li>PyQtGraph — real-time waveform plotting</li>"
            "<li>NumPy — signal processing</li>"
            "<li>PySerial — ESP32-S3 serial bridge</li>"
            "</ul>"
            "<p><b>Hardware:</b> ESP32-S3-DevKitC-1 USB bridge</p>"
        )
        tabs.addTab(about_text, "About")

        # License tab
        license_text = QTextEdit()
        license_text.setReadOnly(True)
        license_text.setFont(QFont("Menlo", 10))
        license_text.setPlainText(self._load_license())
        tabs.addTab(license_text, "License (GPL v3)")

        layout.addWidget(tabs, stretch=1)

        # OK button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)

    @staticmethod
    def _load_license() -> str:
        """Load the LICENSE file from the project root."""
        import os
        license_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "LICENSE",
        )
        try:
            with open(license_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "LICENSE file not found.\n\nThis software is licensed under the GNU General Public License v3.0."


class MainWindow(QMainWindow):
    """Main oscilloscope window.

    Layout:
        - Menu bar at top
        - Toolbar (Run/Stop/Single + status)
        - Main area: waveform (left) | controls (right)
        - Measurement bar below waveform
        - Status bar at bottom
    """

    # Signals to acquisition worker
    sig_set_bridge = Signal(object)
    sig_run_init = Signal()
    sig_start_continuous = Signal()
    sig_start_single = Signal()
    sig_stop = Signal()
    sig_set_vdiv = Signal(int, float)
    sig_set_offset = Signal(int, float)
    sig_set_coupling = Signal(int, str)
    sig_set_bwlimit = Signal(int, bool)
    sig_set_probe = Signal(int, float)
    sig_set_tdiv = Signal(float)
    sig_set_position = Signal(float)
    sig_set_trigger_level = Signal(float)
    sig_set_trigger_source = Signal(str)
    sig_set_trigger_slope = Signal(str)
    sig_set_trigger_sweep = Signal(str)
    sig_set_trigger_coupling = Signal(str)
    sig_set_channel_enabled = Signal(int, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Agilent U2702A Oscilloscope — v{APP_VERSION}")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 900)

        self._bridge = None
        self._is_running = False
        self._scpi_tester = None
        self._channel_colors: dict[int, str] = {}
        self._last_waveforms: dict[int, WaveformData] = {}
        self._trigger_source: str = "CHAN1"  # Track trigger source for offset
        self._zoom_undo_stack: list[dict] = []

        # Initialize default colors
        for ch in range(1, NUM_CHANNELS + 1):
            self._channel_colors[ch] = channel_color(ch)

        # Worker + thread
        self._worker = AcquisitionWorker()
        self._acq_thread = QThread()
        self._worker.moveToThread(self._acq_thread)

        # Build UI
        self._build_menu_bar()
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # Connect signals
        self._connect_signals()
        self._acq_thread.start()

        # Enable default channels on the waveform widget (CH1 on by default)
        for ch in self._channel_panel.get_enabled_channels():
            self._waveform.set_channel_enabled(ch, True)
            self._measurement_bar.set_channel_visible(ch, True)

        # Cmd+Z to undo zoom
        QShortcut(QKeySequence.StandardKey.Undo, self).activated.connect(
            self._on_undo_zoom
        )

        # Auto-show connection dialog on startup
        QTimer.singleShot(200, self._show_connection_dialog)

    def _build_menu_bar(self):
        """Build the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        connect_action = QAction("Connect...", self)
        connect_action.setShortcut("Ctrl+K")
        connect_action.triggered.connect(self._show_connection_dialog)
        file_menu.addAction(connect_action)

        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self._disconnect)
        file_menu.addAction(disconnect_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Tools menu
        tools_menu = menubar.addMenu("Tools")

        scpi_action = QAction("SCPI Tester...", self)
        scpi_action.setShortcut("Ctrl+T")
        scpi_action.triggered.connect(self._open_scpi_tester)
        tools_menu.addAction(scpi_action)

        # Settings menu
        settings_action = QAction("Settings...", self)
        settings_action.setMenuRole(QAction.MenuRole.NoRole)  # Keep visible (macOS moves it otherwise)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        menubar.addAction(settings_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About...", self)
        about_action.setMenuRole(QAction.MenuRole.NoRole)  # Keep in Help menu (macOS moves it otherwise)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self):
        """Build the Run/Stop/Single toolbar."""
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)

        # Run button
        self._run_btn = QPushButton("▶ Run")
        self._run_btn.setFixedHeight(32)
        self._run_btn.setMinimumWidth(80)
        self._run_btn.setStyleSheet(
            "QPushButton { background-color: #2a6e2a; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3a8e3a; }"
            "QPushButton:disabled { background-color: #333333; color: #666666; }"
        )
        self._run_btn.clicked.connect(self._on_run)
        tb_layout.addWidget(self._run_btn)

        # Stop button
        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.setMinimumWidth(80)
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #6e2a2a; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #8e3a3a; }"
            "QPushButton:disabled { background-color: #333333; color: #666666; }"
        )
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        tb_layout.addWidget(self._stop_btn)

        # Single button
        self._single_btn = QPushButton("⎍ Single")
        self._single_btn.setFixedHeight(32)
        self._single_btn.setMinimumWidth(80)
        self._single_btn.setStyleSheet(
            "QPushButton { background-color: #2a4a6e; color: white; "
            "font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3a5a8e; }"
            "QPushButton:disabled { background-color: #333333; color: #666666; }"
        )
        self._single_btn.clicked.connect(self._on_single)
        tb_layout.addWidget(self._single_btn)

        tb_layout.addStretch()

        # FPS label
        self._fps_label = QLabel("")
        self._fps_label.setStyleSheet(
            "color: #555555; font-size: 10px; font-family: Menlo, monospace;"
        )
        tb_layout.addWidget(self._fps_label)

        # Status indicator
        self._status_indicator = StatusIndicator()
        tb_layout.addWidget(self._status_indicator)

        # Add toolbar to layout (will be at the top of central widget)
        self._toolbar_widget = toolbar

    def _build_main_area(self):
        """Build the main content area: waveform left, controls right."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Toolbar at top
        main_layout.addWidget(self._toolbar_widget)

        # Main splitter: waveform | controls
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left side: waveform + measurements ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # Waveform display
        self._waveform = WaveformWidget(num_channels=NUM_CHANNELS)
        self._waveform.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self._waveform, stretch=1)

        # Measurement bar
        self._measurement_bar = MeasurementBar(num_channels=NUM_CHANNELS)
        left_layout.addWidget(self._measurement_bar)

        splitter.addWidget(left_widget)

        # --- Right side: control panels (scrollable) ---
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        right_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 4, 0)
        right_layout.setSpacing(6)

        # Right panel layout order (top to bottom):
        # 0. Utility (Autoscale, measurements toggle, placeholders)
        self._utility_panel = UtilityPanel()
        self._utility_panel.set_autoscale_enabled(False)
        right_layout.addWidget(self._utility_panel)

        # 1. Horizontal (T/div + Position knobs side by side)
        self._timebase_panel = TimebasePanel()
        right_layout.addWidget(self._timebase_panel)

        # 2. Trigger (Level knob + dropdowns)
        self._trigger_panel = TriggerPanel(num_channels=NUM_CHANNELS)
        right_layout.addWidget(self._trigger_panel)

        # 3. Vertical — per-channel columns (like Keysight 1/2/3/4 buttons)
        self._channel_panel = ChannelPanel(num_channels=NUM_CHANNELS)
        right_layout.addWidget(self._channel_panel)

        right_layout.addStretch()
        right_scroll.setWidget(right_widget)

        splitter.addWidget(right_scroll)

        # Set initial sizes: ~70% waveform, ~30% controls
        splitter.setSizes([700, 300])
        splitter.setStretchFactor(0, 1)  # Waveform stretches
        splitter.setStretchFactor(1, 0)  # Controls fixed

        main_layout.addWidget(splitter, stretch=1)

    def _build_status_bar(self):
        """Build the status bar."""
        sb = self.statusBar()
        sb.showMessage("Disconnected — File > Connect to start")

    def _connect_signals(self):
        """Wire up all signal/slot connections."""

        # --- MainWindow → Worker ---
        self.sig_set_bridge.connect(self._worker.set_bridge)
        self.sig_run_init.connect(self._worker.run_init_sequence)
        self.sig_start_continuous.connect(self._worker.start_continuous)
        self.sig_start_single.connect(self._worker.start_single)
        self.sig_stop.connect(self._worker.stop)
        self.sig_set_vdiv.connect(self._worker.set_vdiv)
        self.sig_set_offset.connect(self._worker.set_offset)
        self.sig_set_coupling.connect(self._worker.set_coupling)
        self.sig_set_bwlimit.connect(self._worker.set_bwlimit)
        self.sig_set_probe.connect(self._worker.set_probe)
        self.sig_set_tdiv.connect(self._worker.set_tdiv)
        self.sig_set_position.connect(self._worker.set_position)
        self.sig_set_trigger_level.connect(self._worker.set_trigger_level)
        self.sig_set_trigger_source.connect(self._worker.set_trigger_source)
        self.sig_set_trigger_slope.connect(self._worker.set_trigger_slope)
        self.sig_set_trigger_sweep.connect(self._worker.set_trigger_sweep)
        self.sig_set_trigger_coupling.connect(self._worker.set_trigger_coupling)
        self.sig_set_channel_enabled.connect(self._worker.set_channel_enabled)

        # --- Worker → MainWindow ---
        self._worker.waveform_ready.connect(self._on_waveform_ready)
        self._worker.init_complete.connect(self._on_init_complete)
        self._worker.status_changed.connect(self._on_bridge_status)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.fps_update.connect(self._on_fps_update)

        # --- Channel panel → MainWindow/Worker ---
        self._channel_panel.vdiv_changed.connect(self._on_vdiv_changed)
        self._channel_panel.offset_changed.connect(self._on_offset_changed)
        self._channel_panel.coupling_changed.connect(
            lambda ch, v: self.sig_set_coupling.emit(ch, v)
        )
        self._channel_panel.bwlimit_changed.connect(
            lambda ch, v: self.sig_set_bwlimit.emit(ch, v)
        )
        self._channel_panel.probe_changed.connect(
            lambda ch, v: self.sig_set_probe.emit(ch, v)
        )
        self._channel_panel.channel_enabled.connect(self._on_channel_enabled)

        # --- Timebase panel → Worker ---
        self._timebase_panel.tdiv_changed.connect(self._on_tdiv_changed)
        self._timebase_panel.position_changed.connect(
            self._on_position_changed
        )

        # --- Trigger panel → Worker + Waveform ---
        self._trigger_panel.level_changed.connect(
            self._on_trigger_level_changed
        )
        self._trigger_panel.source_changed.connect(
            self._on_trigger_source_changed
        )
        self._trigger_panel.slope_changed.connect(
            lambda v: self.sig_set_trigger_slope.emit(v)
        )
        self._trigger_panel.sweep_changed.connect(
            lambda v: self.sig_set_trigger_sweep.emit(v)
        )
        self._trigger_panel.coupling_changed.connect(
            lambda v: self.sig_set_trigger_coupling.emit(v)
        )

        # --- Utility panel ---
        self._utility_panel.autoscale_requested.connect(self._on_autoscale)
        self._utility_panel.measurement_bar_toggled.connect(
            self._measurement_bar.setVisible
        )

        # --- Waveform zoom + drag ---
        self._waveform.zoom_requested.connect(self._on_zoom_requested)
        self._waveform.trigger_level_dragged.connect(
            self._on_trigger_level_dragged
        )
        self._waveform.trigger_pos_dragged.connect(
            self._on_trigger_pos_dragged
        )
        self._waveform.offset_dragged.connect(self._on_offset_dragged)

    # --- Toolbar actions ---

    def _on_run(self):
        if not self._bridge:
            self._show_connection_dialog()
            return
        self._is_running = True
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._single_btn.setEnabled(False)
        self._status_indicator.set_status("RUNNING")
        self.sig_start_continuous.emit()

    def _on_stop(self):
        self._is_running = False
        self.sig_stop.emit()
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._single_btn.setEnabled(True)
        self._status_indicator.set_status("STOPPED")
        self._fps_label.setText("")

    def _on_single(self):
        if not self._bridge:
            self._show_connection_dialog()
            return
        self._status_indicator.set_status("RUNNING")
        self.sig_start_single.emit()
        # Single will auto-stop
        QTimer.singleShot(2000, lambda: (
            self._status_indicator.set_status("READY")
            if not self._is_running else None
        ))

    # --- Control panel callbacks ---

    def _on_vdiv_changed(self, ch: int, value: float):
        self.sig_set_vdiv.emit(ch, value)
        # Update waveform display scaling (use active channel's V/div)
        self._waveform.set_scales(value, self._timebase_panel.t_per_div)

    def _on_offset_changed(self, ch: int, value: float):
        self.sig_set_offset.emit(ch, value)
        self._waveform.set_channel_offset(ch, value)
        # If this is the trigger source channel, update trigger line position
        if self._trigger_source == f"CHAN{ch}":
            self._waveform.set_trigger_source_offset(value)

    def _on_position_changed(self, value: float):
        self.sig_set_position.emit(value)
        self._waveform.set_h_position(value)

    def _on_trigger_level_changed(self, value: float):
        self.sig_set_trigger_level.emit(value)
        self._waveform.set_trigger_level(value)

    def _on_trigger_source_changed(self, source: str):
        self.sig_set_trigger_source.emit(source)
        self._trigger_source = source
        # Update trigger line offset to match new source channel
        if source.startswith("CHAN"):
            ch = int(source[4:])
            ch_state = self._channel_panel.get_state(ch)
            self._waveform.set_trigger_source_offset(ch_state.offset)
        else:
            # EXT trigger — no channel offset
            self._waveform.set_trigger_source_offset(0.0)

    def _on_tdiv_changed(self, value: float):
        self.sig_set_tdiv.emit(value)
        # Get current V/div from active channel
        ch_state = self._channel_panel.get_state(
            self._channel_panel._active_channel
        )
        self._waveform.set_scales(ch_state.v_per_div, value)

    def _on_channel_enabled(self, ch: int, enabled: bool):
        self.sig_set_channel_enabled.emit(ch, enabled)
        self._waveform.set_channel_enabled(ch, enabled)
        self._measurement_bar.set_channel_visible(ch, enabled)

    def _on_zoom_requested(self, t_min: float, v_min: float,
                           t_max: float, v_max: float):
        """Handle drag-to-zoom rectangle from waveform widget."""
        # Push current state for Cmd+Z undo
        ch = self._channel_panel._active_channel
        ch_state = self._channel_panel.get_state(ch)
        self._zoom_undo_stack.append({
            'tdiv': self._timebase_panel.t_per_div,
            'h_position': self._timebase_panel.position,
            'channel': ch,
            'vdiv': ch_state.v_per_div,
            'offset': ch_state.offset,
        })
        if len(self._zoom_undo_stack) > 20:
            self._zoom_undo_stack.pop(0)

        time_range = t_max - t_min
        volt_range = v_max - v_min

        # Snap T/div: smallest TDIV where full display >= selected range
        num_h = WaveformWidget.NUM_H_DIVS
        new_tdiv = TDIV_VALUES[-1]
        for tdiv in TDIV_VALUES:
            if num_h * tdiv >= time_range:
                new_tdiv = tdiv
                break

        # Snap V/div: smallest VDIV where full display >= selected range
        num_v = WaveformWidget.NUM_V_DIVS
        new_vdiv = VDIV_VALUES[-1]
        for vdiv in VDIV_VALUES:
            if num_v * vdiv >= volt_range:
                new_vdiv = vdiv
                break

        # H position: center of selected time range
        new_h_pos = (t_min + t_max) / 2

        # V offset (active channel): shift so selection is centered at y=0
        new_offset = -(v_min + v_max) / 2

        # Apply T/div + position
        self._timebase_panel.set_tdiv(new_tdiv)
        self.sig_set_tdiv.emit(new_tdiv)
        self._timebase_panel.set_position(new_h_pos)
        self.sig_set_position.emit(new_h_pos)

        # Apply V/div + offset (active channel)
        ch = self._channel_panel._active_channel
        self._channel_panel.set_channel_state(
            ch, v_per_div=new_vdiv, offset=new_offset
        )
        self._channel_panel._states[ch].v_per_div = new_vdiv
        self._channel_panel._states[ch].offset = new_offset
        self.sig_set_vdiv.emit(ch, new_vdiv)
        self.sig_set_offset.emit(ch, new_offset)

        # Update waveform display
        self._waveform.set_scales(new_vdiv, new_tdiv)
        self._waveform.set_h_position(new_h_pos)
        self._waveform.set_channel_offset(ch, new_offset)

        # Update trigger line if this is the trigger source
        if self._trigger_source == f"CHAN{ch}":
            self._waveform.set_trigger_source_offset(new_offset)

    def _on_undo_zoom(self):
        """Undo the last zoom operation (Cmd+Z)."""
        if not self._zoom_undo_stack:
            self.statusBar().showMessage("Nothing to undo", 2000)
            return

        snap = self._zoom_undo_stack.pop()
        ch = snap['channel']

        # Restore T/div + position
        self._timebase_panel.set_tdiv(snap['tdiv'])
        self.sig_set_tdiv.emit(snap['tdiv'])
        self._timebase_panel.set_position(snap['h_position'])
        self.sig_set_position.emit(snap['h_position'])

        # Restore V/div + offset
        self._channel_panel.set_channel_state(
            ch, v_per_div=snap['vdiv'], offset=snap['offset']
        )
        self.sig_set_vdiv.emit(ch, snap['vdiv'])
        self.sig_set_offset.emit(ch, snap['offset'])

        # Update waveform display
        self._waveform.set_scales(snap['vdiv'], snap['tdiv'])
        self._waveform.set_h_position(snap['h_position'])
        self._waveform.set_channel_offset(ch, snap['offset'])

        if self._trigger_source == f"CHAN{ch}":
            self._waveform.set_trigger_source_offset(snap['offset'])

        self.statusBar().showMessage("Zoom undone", 1500)

    def _on_trigger_level_dragged(self, level: float):
        """Handle trigger level dragged on the waveform graph."""
        self._trigger_panel.set_level(level)
        self.sig_set_trigger_level.emit(level)

    def _on_trigger_pos_dragged(self, h_pos: float):
        """Handle trigger position marker dragged on the graph."""
        self._timebase_panel.set_position(h_pos)
        self.sig_set_position.emit(h_pos)

    def _on_offset_dragged(self, ch: int, offset: float):
        """Handle channel GND marker dragged on the graph."""
        self._channel_panel.set_channel_state(ch, offset=offset)
        self.sig_set_offset.emit(ch, offset)
        if self._trigger_source == f"CHAN{ch}":
            self._waveform.set_trigger_source_offset(offset)

    # --- Worker callbacks ---

    @Slot(object)
    def _on_waveform_ready(self, waveform: WaveformData):
        """Handle new waveform data from worker."""
        self._last_waveforms[waveform.channel] = waveform  # Cache for autoscale
        self._waveform.update_waveform(waveform)

        # Compute and display measurements
        meas = measurements.compute_all(waveform.voltage, waveform.time_axis)
        self._measurement_bar.update_measurements(waveform.channel, meas)

    @Slot(dict)
    def _on_init_complete(self, state: dict):
        """Handle init sequence complete — apply instrument state to GUI."""
        # Apply channel states
        for ch, ch_state in state.get("channels", {}).items():
            self._channel_panel.set_channel_state(
                ch,
                enabled=ch_state.get("enabled"),
                v_per_div=ch_state.get("v_per_div"),
                offset=ch_state.get("offset"),
                coupling=ch_state.get("coupling"),
                bw_limit=ch_state.get("bw_limit"),
            )

            # Update worker's channel settings
            enabled = ch_state.get("enabled", False)
            self.sig_set_channel_enabled.emit(ch, enabled)
            self._waveform.set_channel_enabled(ch, enabled)
            self._measurement_bar.set_channel_visible(ch, enabled)

            # Update GND marker position from offset
            if "offset" in ch_state:
                self._waveform.set_channel_offset(ch, ch_state["offset"])

        # Apply timebase
        tb = state.get("timebase", {})
        if "t_per_div" in tb:
            self._timebase_panel.set_tdiv(tb["t_per_div"])
        if "position" in tb:
            self._timebase_panel.set_position(tb["position"])
            self._waveform.set_h_position(tb["position"])

        # Apply trigger
        trig = state.get("trigger", {})
        if "source" in trig:
            self._trigger_panel.set_source(trig["source"])
            self._trigger_source = trig["source"]
        if "level" in trig:
            self._trigger_panel.set_level(trig["level"])
            self._waveform.set_trigger_level(trig["level"])

        # Sync trigger level line with source channel's offset
        if self._trigger_source.startswith("CHAN"):
            src_ch = int(self._trigger_source[4:])
            channels = state.get("channels", {})
            src_offset = channels.get(src_ch, {}).get("offset", 0.0)
            self._waveform.set_trigger_source_offset(src_offset)
        if "slope" in trig:
            self._trigger_panel.set_slope(trig["slope"])
        if "sweep" in trig:
            self._trigger_panel.set_sweep(trig["sweep"])
        if "coupling" in trig:
            self._trigger_panel.set_coupling(trig["coupling"])

        # Update waveform scale
        active_ch = self._channel_panel._active_channel
        ch_st = self._channel_panel.get_state(active_ch)
        self._waveform.set_scales(
            ch_st.v_per_div,
            self._timebase_panel.t_per_div,
        )

        self._status_indicator.set_status("READY")
        self.statusBar().showMessage("Instrument initialized — Ready")

    @Slot(str)
    def _on_bridge_status(self, status: str):
        self._status_indicator.set_status(status)

    @Slot(str)
    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"Error: {msg}", 5000)

    @Slot(float)
    def _on_fps_update(self, fps: float):
        self._fps_label.setText(f"{fps:.1f} fps")

    # --- Connection ---

    def _show_connection_dialog(self):
        """Show the connection dialog."""
        dialog = ConnectionDialog(self)
        dialog.connection_established.connect(self._on_connected)
        dialog.exec()

    def _on_connected(self, bridge):
        """Handle new connection from dialog."""
        self._bridge = bridge
        self.sig_set_bridge.emit(bridge)
        self._status_indicator.set_status("CONNECTED")
        self._utility_panel.set_autoscale_enabled(True)
        self.statusBar().showMessage(
            f"Connected: {bridge.port} — Initializing..."
        )

        # Run init sequence
        self.sig_run_init.emit()

    def _disconnect(self):
        """Disconnect from instrument."""
        if self._is_running:
            self._on_stop()

        if self._bridge:
            self._bridge.close()
            self._bridge = None

        self._utility_panel.set_autoscale_enabled(False)
        self._last_waveforms.clear()
        self._status_indicator.set_status("DISCONNECTED")
        self.statusBar().showMessage("Disconnected")

    # --- SCPI Tester ---

    def _open_scpi_tester(self):
        """Open SCPI Tester window (shared connection)."""
        # Pause acquisition while tester is open
        was_running = self._is_running
        if was_running:
            self._on_stop()

        from gui.scpi_tester import SCPITesterWindow
        self._scpi_tester = SCPITesterWindow(bridge=self._bridge)
        self._scpi_tester.show()

        # Resume when tester closes
        if was_running:
            self._scpi_tester.destroyed.connect(self._on_run)

    # --- Settings ---

    def _open_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(
            num_channels=NUM_CHANNELS,
            current_colors=self._channel_colors,
            parent=self,
        )

        dialog.channel_color_changed.connect(self._on_color_changed)

        if dialog.exec():
            # Apply probe settings
            probes = dialog.get_probe_factors()
            for ch, factor in probes.items():
                self.sig_set_probe.emit(ch, factor)

    def _on_color_changed(self, ch: int, color: str):
        """Handle channel color change from settings."""
        self._channel_colors[ch] = color
        self._waveform.set_channel_color(ch, color)

    # --- Autoscale ---

    def _on_autoscale(self):
        """Software autoscale — analyze cached waveforms and adjust settings."""
        if not self._last_waveforms:
            self.statusBar().showMessage(
                "Autoscale: No waveform data — run acquisition first", 3000
            )
            return

        best_tdiv = None

        for ch, wf in self._last_waveforms.items():
            # 1. Pick V/div based on Vpp
            signal_vpp = measurements.vpp(wf.voltage)
            new_vdiv = pick_vdiv(signal_vpp, VDIV_VALUES)

            # 2. Center the signal vertically
            new_offset = compute_center_offset(wf.voltage)

            # 3. Apply to instrument + GUI
            self._channel_panel.set_channel_state(
                ch, v_per_div=new_vdiv, offset=new_offset
            )
            self.sig_set_vdiv.emit(ch, new_vdiv)
            self.sig_set_offset.emit(ch, new_offset)
            self._waveform.set_channel_offset(ch, new_offset)

            # 4. Pick T/div from first channel with detectable frequency
            if best_tdiv is None:
                freq = measurements.frequency(wf.voltage, wf.time_axis)
                candidate = pick_tdiv(freq, TDIV_VALUES)
                if candidate is not None:
                    best_tdiv = candidate

        # Apply T/div (shared across all channels)
        if best_tdiv is not None:
            self._timebase_panel.set_tdiv(best_tdiv)
            self.sig_set_tdiv.emit(best_tdiv)

        # Update waveform widget scaling
        active_ch = self._channel_panel._active_channel
        ch_st = self._channel_panel.get_state(active_ch)
        tdiv = best_tdiv if best_tdiv else self._timebase_panel.t_per_div
        self._waveform.set_scales(ch_st.v_per_div, tdiv)

        self.statusBar().showMessage("Autoscale complete", 2000)

    # --- About ---

    def _show_about(self):
        """Show About/License dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    # --- Cleanup ---

    def closeEvent(self, event):
        """Clean shutdown."""
        if self._is_running:
            self.sig_stop.emit()

        if self._bridge:
            self._bridge.close()

        self._acq_thread.quit()
        self._acq_thread.wait(3000)

        super().closeEvent(event)
