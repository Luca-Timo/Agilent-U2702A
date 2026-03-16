"""
Main oscilloscope window — graph left, controls right.

Wires together all components: waveform display, control panels,
acquisition worker, connection dialog, settings, and SCPI tester.
"""

import sys
import os

from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer, QSettings
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QMenuBar, QStatusBar, QSizePolicy,
    QFrame, QScrollArea, QApplication, QDialog, QTextEdit,
    QDialogButtonBox, QTabWidget, QFileDialog,
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
from gui.cursor_readout import CursorReadout
from gui.acquisition_worker import AcquisitionWorker
from gui.connection_dialog import ConnectionDialog
from gui.settings_dialog import SettingsDialog
from gui.dmm_widget import DMMWidget
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
        self.setText(f"  {status}  ")
        self.setStyleSheet(
            f"background-color: {color}; color: white; "
            f"border-radius: 4px; padding: 2px 8px; "
            f"font-weight: bold; font-size: 11px; "
            f"font-family: Menlo, monospace;"
        )


APP_VERSION = "0.8.2-alpha"
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
        self._time_cursors: dict[int, float] = {1: 0.0, 2: 0.0}
        self._volt_cursors: dict[int, float] = {1: 0.0, 2: 0.0}
        self._dmm_mode: bool = False
        self._dmm_auto_started: bool = False  # True if DMM auto-started acquisition
        self._dmm_ar_counter: dict[int, int] = {}  # auto-range frame counter
        self._cursor_channel: int = 1    # which channel Y cursors measure
        self._hold_active: bool = False
        self._rel_active: bool = False
        self._rel_refs: dict[int, float] = {}  # per-channel reference primary
        self._range_locked: bool = False
        self._settings = QSettings("AgilentU2702A", "Oscilloscope")
        self._recent_files: list[str] = []
        self._current_session_path: str | None = None

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

        # Load QSettings (recent files, last port/baud)
        self._load_qsettings()

        # Auto-restore last session, then show connection dialog
        QTimer.singleShot(0, self._auto_restore_session)

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

        save_action = QAction("Save Session", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save_session)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Session As…", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_session_as)
        file_menu.addAction(save_as_action)

        load_action = QAction("Load Session…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._on_load_session)
        file_menu.addAction(load_action)

        # Recent Sessions submenu
        self._recent_menu = file_menu.addMenu("Recent Sessions")
        self._update_recent_files_menu()

        file_menu.addSeparator()

        reset_action = QAction("Reset Session", self)
        reset_action.triggered.connect(self._on_reset_session)
        file_menu.addAction(reset_action)

        file_menu.addSeparator()

        export_action = QAction("Export…", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        export_csv_action = QAction("Quick Export CSV", self)
        export_csv_action.setShortcut("Ctrl+Shift+E")
        export_csv_action.triggered.connect(self._on_quick_export_csv)
        file_menu.addAction(export_csv_action)

        import_action = QAction("Import…", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self._on_import)
        file_menu.addAction(import_action)

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

        tools_menu.addSeparator()

        settings_action = QAction("Settings...", self)
        settings_action.setMenuRole(QAction.MenuRole.NoRole)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        tools_menu.addAction(settings_action)

        tools_menu.addSeparator()

        probe_comp_action = QAction("Probe Compensation...", self)
        probe_comp_action.triggered.connect(self._show_probe_compensation)
        tools_menu.addAction(probe_comp_action)

        self_cal_action = QAction("Self-Calibration...", self)
        self_cal_action.triggered.connect(self._show_self_calibration)
        tools_menu.addAction(self_cal_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About...", self)
        about_action.setMenuRole(QAction.MenuRole.NoRole)  # Keep in Help menu (macOS moves it otherwise)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    _TB_BTN_HEIGHT = 28   # Uniform height for toolbar buttons & indicators
    _TB_BTN_MIN_W = 80    # Minimum width for Run/Stop/Single buttons
    _TB_FONT = "font-size: 11px; font-weight: bold; font-family: Menlo, monospace;"

    @staticmethod
    def _tb_btn_style(bg: str, hover: str) -> str:
        """Generate toolbar button stylesheet."""
        font = MainWindow._TB_FONT
        return (
            f"QPushButton {{ background-color: {bg}; color: white; "
            f"{font} border-radius: 4px; padding: 0 12px; }}"
            f"QPushButton:hover {{ background-color: {hover}; }}"
            f"QPushButton:disabled {{ background-color: #333333; color: #666666; }}"
        )

    def _build_toolbar(self):
        """Build the Run/Stop/Single toolbar."""
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)

        # Run button
        self._run_btn = QPushButton("▶ Run")
        self._run_btn.setFixedHeight(self._TB_BTN_HEIGHT)
        self._run_btn.setMinimumWidth(self._TB_BTN_MIN_W)
        self._run_btn.setStyleSheet(
            self._tb_btn_style("#2a6e2a", "#3a8e3a")
        )
        self._run_btn.clicked.connect(self._on_run)
        tb_layout.addWidget(self._run_btn)

        # Stop button
        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setFixedHeight(self._TB_BTN_HEIGHT)
        self._stop_btn.setMinimumWidth(self._TB_BTN_MIN_W)
        self._stop_btn.setStyleSheet(
            self._tb_btn_style("#6e2a2a", "#8e3a3a")
        )
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        tb_layout.addWidget(self._stop_btn)

        # Single button
        self._single_btn = QPushButton("⎍ Single")
        self._single_btn.setFixedHeight(self._TB_BTN_HEIGHT)
        self._single_btn.setMinimumWidth(self._TB_BTN_MIN_W)
        self._single_btn.setStyleSheet(
            self._tb_btn_style("#2a4a6e", "#3a5a8e")
        )
        self._single_btn.clicked.connect(self._on_single)
        tb_layout.addWidget(self._single_btn)

        tb_layout.addStretch()

        # FPS label (fixed width to prevent layout shift)
        self._fps_label = QLabel("")
        self._fps_label.setFixedHeight(self._TB_BTN_HEIGHT)
        self._fps_label.setFixedWidth(72)
        self._fps_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
        self._fps_label.setStyleSheet(
            f"color: #555555; {self._TB_FONT} padding: 0 4px;"
        )
        tb_layout.addWidget(self._fps_label)

        # Trigger status indicator (fixed width to prevent layout shift)
        self._trigger_status_label = QLabel("")
        self._trigger_status_label.setFixedHeight(self._TB_BTN_HEIGHT)
        self._trigger_status_label.setFixedWidth(72)
        self._trigger_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._trigger_status_label.setStyleSheet(
            f"color: #888888; {self._TB_FONT} padding: 2px 6px;"
        )
        tb_layout.addWidget(self._trigger_status_label)

        # Status indicator
        self._status_indicator = StatusIndicator()
        self._status_indicator.setFixedHeight(self._TB_BTN_HEIGHT)
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

        # DMM display (hidden until DMM mode activated)
        self._dmm_widget = DMMWidget(num_channels=NUM_CHANNELS)
        self._dmm_widget.setVisible(False)
        left_layout.addWidget(self._dmm_widget, stretch=1)

        # Cursor readout (between waveform and measurement bar)
        self._cursor_readout = CursorReadout()
        self._cursor_readout.setVisible(False)  # Hidden until cursors enabled
        left_layout.addWidget(self._cursor_readout)

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

        # Scope-only panels — hidden during DMM mode
        self._scope_panels = [self._timebase_panel, self._trigger_panel]

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
        self._worker.trigger_status.connect(self._on_trigger_status)

        # --- Channel panel → MainWindow/Worker ---
        self._channel_panel.vdiv_changed.connect(self._on_vdiv_changed)
        self._channel_panel.offset_changed.connect(self._on_offset_changed)
        self._channel_panel.coupling_changed.connect(
            lambda ch, v: self.sig_set_coupling.emit(ch, v)
        )
        self._channel_panel.bwlimit_changed.connect(
            lambda ch, v: self.sig_set_bwlimit.emit(ch, v)
        )
        self._channel_panel.probe_changed.connect(self._on_probe_changed)
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
        self._trigger_panel.slope_changed.connect(self._on_trigger_slope_changed)
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
        self._waveform.cursor_moved.connect(self._on_cursor_moved)

        # --- Cursor controls ---
        self._utility_panel.cursor_mode_changed.connect(
            self._on_cursor_mode_changed
        )
        self._utility_panel.cursor_reset_requested.connect(
            self._on_cursor_reset
        )
        self._cursor_readout.channel_selected.connect(
            self._on_cursor_channel_selected
        )

        # --- DMM mode ---
        self._utility_panel.dmm_mode_toggled.connect(
            self._on_dmm_mode_toggled
        )
        self._utility_panel.hold_toggled.connect(self._on_hold_toggled)
        self._utility_panel.relative_toggled.connect(self._on_relative_toggled)
        self._utility_panel.range_lock_toggled.connect(self._on_range_lock_toggled)
        self._dmm_widget.mode_changed.connect(self._on_dmm_measurement_mode_changed)

        # --- Current mode ---
        self._channel_panel.current_mode_changed.connect(
            self._on_current_mode_changed
        )

        # --- Measurement hover → highlight lines ---
        self._measurement_bar.value_hovered.connect(
            self._on_measurement_hovered
        )
        self._measurement_bar.value_unhovered.connect(
            self._waveform.hide_measurement_highlight
        )
        # --- Measurement click → set cursors ---
        self._measurement_bar.value_clicked.connect(
            self._on_measurement_clicked
        )

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
        self._trigger_status_label.setText("")
        self._trigger_status_label.setStyleSheet("")

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

    def _effective_vdiv(self, ch: int) -> float:
        """Get effective V/div (raw × probe factor) for display scaling."""
        st = self._channel_panel.get_state(ch)
        return st.v_per_div * st.probe_factor

    def _on_vdiv_changed(self, ch: int, value: float):
        self.sig_set_vdiv.emit(ch, value)
        # Always update this channel's effective V/div for per-channel scaling
        probe = self._channel_panel.get_state(ch).probe_factor
        effective = value * probe
        self._waveform.set_channel_vdiv(ch, effective)
        # Only update the display axis (grid) if this is the active channel
        if ch == self._channel_panel._active_channel:
            self._waveform.set_scales(
                effective, self._timebase_panel.t_per_div
            )
        # Refresh cursor readout (V/div ratio changed)
        if self._waveform._cursor_mode in ("voltage", "both"):
            self._push_volt_cursor_readout()

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

    def _on_probe_changed(self, ch: int, factor: float):
        self.sig_set_probe.emit(ch, factor)
        old_display_vdiv = self._waveform._v_per_div
        self._waveform.set_channel_probe(ch, factor)
        # Always update this channel's effective V/div for per-channel scaling
        vdiv = self._channel_panel.get_state(ch).v_per_div
        effective = vdiv * factor
        self._waveform.set_channel_vdiv(ch, effective)
        # Only refresh the display axis (grid) if this is the active channel
        if ch == self._channel_panel._active_channel:
            self._waveform.set_scales(
                effective, self._timebase_panel.t_per_div
            )
            # Rescale volt cursor positions: traces moved by
            # new_display_vdiv / old_display_vdiv, so cursors must follow.
            new_display_vdiv = self._waveform._v_per_div
            if (old_display_vdiv > 0 and new_display_vdiv != old_display_vdiv
                    and self._waveform._cursor_mode in ("voltage", "both")):
                ratio = new_display_vdiv / old_display_vdiv
                for i in range(2):
                    self._waveform._volt_cursors[i] *= ratio
                    if self._waveform._volt_cursor_lines[i] is not None:
                        self._waveform._volt_cursor_lines[i].setPos(
                            self._waveform._volt_cursors[i])
                self._waveform._update_cursor_positions()
                self._volt_cursors = {
                    1: self._waveform._volt_cursors[0],
                    2: self._waveform._volt_cursors[1],
                }
        # Refresh cursor readout (effective V/div changed)
        if self._waveform._cursor_mode in ("voltage", "both"):
            self._push_volt_cursor_readout()
        # Recompute measurements with the new probe factor so the
        # measurement bar updates immediately (without waiting for the
        # next acquisition frame).
        self._recompute_channel_measurements(ch)

    def _on_trigger_slope_changed(self, slope: str):
        self.sig_set_trigger_slope.emit(slope)
        self._waveform.set_trigger_slope(slope)

    def _on_trigger_source_changed(self, source: str):
        self.sig_set_trigger_source.emit(source)
        self._trigger_source = source
        # Update trigger line offset to match new source channel
        if source.startswith("CHAN"):
            ch = int(source[4:])
            ch_state = self._channel_panel.get_state(ch)
            self._waveform.set_trigger_source_channel(ch)
            self._waveform.set_trigger_source_offset(ch_state.offset)
        else:
            # EXT trigger — no channel offset
            self._waveform.set_trigger_source_channel(1)
            self._waveform.set_trigger_source_offset(0.0)

    def _on_tdiv_changed(self, value: float):
        self.sig_set_tdiv.emit(value)
        # Get effective V/div from active channel (raw × probe)
        active = self._channel_panel._active_channel
        self._waveform.set_scales(self._effective_vdiv(active), value)

    def _on_channel_enabled(self, ch: int, enabled: bool):
        self.sig_set_channel_enabled.emit(ch, enabled)
        self._waveform.set_channel_enabled(ch, enabled)
        self._measurement_bar.set_channel_visible(ch, enabled)
        self._dmm_widget.set_channel_visible(ch, enabled)

    # --- Cursor callbacks ---

    def _on_cursor_mode_changed(self, mode: str):
        """Handle cursor mode changed from utility panel combo."""
        self._waveform.set_cursor_mode(mode)
        self._cursor_readout.set_mode(mode)
        self._cursor_readout.setVisible(mode != "off")

        # Push initial cursor values to the readout
        if mode in ("time", "both"):
            t1 = self._waveform._time_cursors[0]
            t2 = self._waveform._time_cursors[1]
            self._time_cursors = {1: t1, 2: t2}
            self._cursor_readout.update_time_cursors(t1, t2)
        if mode in ("voltage", "both"):
            v1 = self._waveform._volt_cursors[0]
            v2 = self._waveform._volt_cursors[1]
            self._volt_cursors = {1: v1, 2: v2}
            self._push_volt_cursor_readout()

    def _on_cursor_reset(self):
        """Reset cursor positions to ±25% of the visible range."""
        self._waveform.reset_cursor_positions()
        # Sync readout with new positions
        mode = self._waveform._cursor_mode
        if mode in ("time", "both"):
            t1 = self._waveform._time_cursors[0]
            t2 = self._waveform._time_cursors[1]
            self._time_cursors = {1: t1, 2: t2}
            self._cursor_readout.update_time_cursors(t1, t2)
        if mode in ("voltage", "both"):
            v1 = self._waveform._volt_cursors[0]
            v2 = self._waveform._volt_cursors[1]
            self._volt_cursors = {1: v1, 2: v2}
            self._push_volt_cursor_readout()

    # --- DMM mode ---

    def _on_dmm_mode_toggled(self, active: bool):
        """Toggle between oscilloscope and DMM display modes."""
        self._dmm_mode = active

        # Swap visibility: waveform ↔ DMM widget
        self._waveform.setVisible(not active)
        self._dmm_widget.setVisible(active)

        # Hide/show scope-only elements
        self._cursor_readout.setVisible(
            not active and self._waveform._cursor_mode != "off"
        )
        # Respect the measurement toggle state when restoring
        meas_visible = self._utility_panel._meas_visible if not active else False
        self._measurement_bar.setVisible(meas_visible)
        for panel in self._scope_panels:
            panel.setVisible(not active)

        if active:
            # Reset DMM accumulators and sync channel visibility
            self._dmm_widget.reset_all()
            self._dmm_ar_counter.clear()
            for ch in range(1, NUM_CHANNELS + 1):
                enabled = ch in self._channel_panel.get_enabled_channels()
                self._dmm_widget.set_channel_visible(ch, enabled)
                self._dmm_widget.set_channel_color(
                    ch, self._channel_colors.get(ch, channel_color(ch))
                )
            # Auto-start continuous acquisition if not already running
            if not self._is_running and self._bridge:
                self._dmm_auto_started = True
                self._on_run()
        else:
            # Auto-stop if we auto-started for DMM
            if self._dmm_auto_started:
                self._dmm_auto_started = False
                self._on_stop()

    def _on_hold_toggled(self, active: bool):
        """Toggle Hold — freeze DMM readings."""
        self._hold_active = active
        self._dmm_widget.set_hold_indicator(active)

    def _on_relative_toggled(self, active: bool):
        """Toggle Relative (Δ) mode — show delta from reference."""
        self._rel_active = active
        if active:
            # Capture current primary reading per channel as reference
            self._rel_refs.clear()
            for ch, acc in self._dmm_widget._accumulators.items():
                last = acc.reading
                if last is not None:
                    self._rel_refs[ch] = last.primary
            self._dmm_widget.set_relative_mode(True, self._rel_refs)
        else:
            self._rel_refs.clear()
            self._dmm_widget.set_relative_mode(False)

    def _on_range_lock_toggled(self, active: bool):
        """Toggle Range Lock — disable DMM auto-range."""
        self._range_locked = active

    def _on_dmm_measurement_mode_changed(self, mode: str):
        """Handle DC/AC mode change — auto-deactivate REL (values incomparable)."""
        if self._rel_active:
            self._utility_panel.set_relative(False)

    def _on_current_mode_changed(self, ch: int, active: bool, shunt_r: float):
        """Handle current mode toggle from channel panel."""
        self._waveform.set_channel_current_mode(ch, active, shunt_r)
        self._measurement_bar.set_channel_current_mode(ch, active)
        self._dmm_widget.set_channel_current_mode(ch, active)
        # If cursor channel matches, update readout unit and re-push values
        if ch == self._cursor_channel:
            self._sync_cursor_channel_mode()
        # Recompute measurements with the new shunt resistance / mode
        self._recompute_channel_measurements(ch)

    def _on_cursor_channel_selected(self, ch: int):
        """Handle channel selector click on cursor readout bar."""
        self._cursor_channel = ch
        self._waveform._cursor_channel = ch
        self._sync_cursor_channel_mode()

    def _sync_cursor_channel_mode(self):
        """Sync cursor readout unit and waveform badges to the cursor channel."""
        ch = self._cursor_channel
        ch_state = self._channel_panel.get_state(ch)
        is_current = ch_state.current_mode
        self._cursor_readout.set_current_mode(is_current)
        self._waveform.set_cursor_current_mode(is_current, channel=ch)
        # Re-push converted values
        mode = self._waveform._cursor_mode
        if mode in ("voltage", "both"):
            self._push_volt_cursor_readout()

    def _cursor_display_to_physical(self, display_y: float) -> float:
        """Convert a Y cursor display position to physical units.

        Reverses the display scaling (_voltage_scale) to recover
        scope-space voltage, then applies the authoritative probe
        factor from the channel panel to get probe-tip voltage
        (or current if in current mode).
        """
        ch = self._cursor_channel
        scale = self._waveform._voltage_scale(ch)
        if abs(scale) < 1e-15:
            return display_y

        # display_y = scope_voltage * scale  →  scope_voltage = display_y / scale
        scope_v = display_y / scale
        ch_state = self._channel_panel.get_state(ch)
        physical = scope_v * ch_state.probe_factor

        if ch_state.current_mode and ch_state.shunt_resistance > 0:
            physical /= ch_state.shunt_resistance

        return physical

    def _push_volt_cursor_readout(self):
        """Convert display-space cursor values to physical and push to readout."""
        v1 = self._cursor_display_to_physical(self._volt_cursors[1])
        v2 = self._cursor_display_to_physical(self._volt_cursors[2])
        self._cursor_readout.update_volt_cursors(v1, v2)

    def _on_cursor_moved(self, cursor_type: str, cursor_id: int, value: float):
        """Handle cursor dragged on waveform graph.

        Args:
            cursor_type: "time" or "voltage"
            cursor_id: 1 or 2 (from signal, 1-indexed)
            value: New position value (seconds or volts)
        """
        if cursor_type == "time":
            self._time_cursors[cursor_id] = value
            self._cursor_readout.update_time_cursors(
                self._time_cursors[1], self._time_cursors[2]
            )
        elif cursor_type == "voltage":
            self._volt_cursors[cursor_id] = value
            self._push_volt_cursor_readout()

    def _on_measurement_hovered(self, ch: int, display_name: str, meas: dict):
        """Show highlight lines on waveform when hovering a measurement value.

        Maps each measurement type to the appropriate horizontal/vertical
        lines to visualize what's being measured.
        """
        color = self._channel_colors.get(ch, channel_color(ch))
        h_lines: list[float] = []   # horizontal (voltage) lines
        v_lines: list[float] = []   # vertical (time) lines

        v_min = meas.get("vmin")
        v_max = meas.get("vmax")

        if display_name == "Vpp":
            if v_min is not None:
                h_lines.append(v_min)
            if v_max is not None:
                h_lines.append(v_max)
        elif display_name == "Vmin":
            if v_min is not None:
                h_lines.append(v_min)
        elif display_name == "Vmax":
            if v_max is not None:
                h_lines.append(v_max)
        elif display_name == "Vrms":
            v = meas.get("vrms")
            if v is not None:
                h_lines.append(v)
        elif display_name == "Vmean":
            v = meas.get("vmean")
            if v is not None:
                h_lines.append(v)
        elif display_name in ("Freq", "Period"):
            period = meas.get("period")
            if period is not None:
                # Show one period centered on trigger (t=0)
                v_lines.append(-period / 2)
                v_lines.append(period / 2)
        elif display_name in ("Rise", "Fall"):
            # Show 10% and 90% threshold levels + time markers
            if v_min is not None and v_max is not None:
                amplitude = v_max - v_min
                if amplitude > 1e-9:
                    h_lines.append(v_min + 0.1 * amplitude)  # 10%
                    h_lines.append(v_min + 0.9 * amplitude)  # 90%
            # Add vertical time markers at the crossing positions
            wf = self._last_waveforms.get(ch)
            if wf is not None:
                probe = wf.probe_factor
                meas_v = wf.voltage * probe if probe != 1.0 else wf.voltage
                if display_name == "Rise":
                    pos = measurements.rise_positions(meas_v, wf.time_axis)
                else:
                    pos = measurements.fall_positions(meas_v, wf.time_axis)
                if pos is not None:
                    v_lines.append(pos[0])
                    v_lines.append(pos[1])
        elif display_name == "Duty":
            # Show midpoint threshold used by duty cycle algorithm
            if v_min is not None and v_max is not None:
                h_lines.append((v_min + v_max) / 2)

        if h_lines or v_lines:
            # Scale voltage highlight lines by per-channel factor so they
            # align with the channel's scaled waveform on screen.
            scale = self._waveform._ch_scale(ch)
            scaled_h = [v * scale for v in h_lines]
            self._waveform.show_measurement_highlight(scaled_h, v_lines, color)

    def _on_measurement_clicked(self, ch: int, display_name: str, meas: dict):
        """Move user cursors to the clicked measurement's key positions.

        Voltage measurements → voltage cursors.
        Time measurements → time cursors.
        """
        v_min = meas.get("vmin")
        v_max = meas.get("vmax")
        scale = self._waveform._ch_scale(ch)

        if display_name == "Vpp":
            if v_min is not None and v_max is not None:
                self._set_cursor_pair("voltage", v_min * scale, v_max * scale)
        elif display_name == "Vmin":
            if v_min is not None:
                vmean = meas.get("vmean")
                v2 = vmean * scale if vmean is not None else 0.0
                self._set_cursor_pair("voltage", v_min * scale, v2)
        elif display_name == "Vmax":
            if v_max is not None:
                vmean = meas.get("vmean")
                v2 = vmean * scale if vmean is not None else 0.0
                self._set_cursor_pair("voltage", v_max * scale, v2)
        elif display_name == "Vrms":
            v = meas.get("vrms")
            if v is not None:
                self._set_cursor_pair("voltage", v * scale, -v * scale)
        elif display_name == "Vmean":
            v = meas.get("vmean")
            if v is not None:
                self._set_cursor_pair("voltage", v * scale, 0.0)
        elif display_name in ("Freq", "Period"):
            period = meas.get("period")
            if period is not None:
                self._set_cursor_pair("time", -period / 2, period / 2)
        elif display_name in ("Rise", "Fall"):
            wf = self._last_waveforms.get(ch)
            if wf is not None:
                probe = wf.probe_factor
                meas_v = wf.voltage * probe if probe != 1.0 else wf.voltage
                if display_name == "Rise":
                    pos = measurements.rise_positions(meas_v, wf.time_axis)
                else:
                    pos = measurements.fall_positions(meas_v, wf.time_axis)
                if pos is not None:
                    self._set_cursor_pair("time", pos[0], pos[1])
                # Also place voltage cursors at 10%/90% thresholds
                if v_min is not None and v_max is not None:
                    amplitude = v_max - v_min
                    if amplitude > 1e-9:
                        thresh_lo = v_min + 0.1 * amplitude
                        thresh_hi = v_min + 0.9 * amplitude
                        self._set_cursor_pair("voltage",
                                              thresh_lo * scale,
                                              thresh_hi * scale)
        elif display_name == "Duty":
            # Place time cursors spanning one period
            period = meas.get("period")
            if period is not None:
                self._set_cursor_pair("time", -period / 2, period / 2)

    def _set_cursor_pair(self, kind: str, c1: float, c2: float):
        """Activate cursor mode and position both cursors.

        Args:
            kind: "time" or "voltage"
            c1: Position for cursor 1.
            c2: Position for cursor 2.
        """
        current_mode = self._waveform._cursor_mode

        # Determine the mode we need
        if kind == "time":
            need_mode = "time" if current_mode in ("off", "time") else "both"
        else:
            need_mode = "voltage" if current_mode in ("off", "voltage") else "both"

        # Switch mode if needed
        if current_mode != need_mode:
            self._waveform.set_cursor_mode(need_mode)
            self._utility_panel.set_cursor_mode(need_mode)
            self._cursor_readout.set_mode(need_mode)
            self._cursor_readout.setVisible(True)

        # Position the cursors
        if kind == "time":
            self._waveform.set_time_cursor(0, c1)
            self._waveform.set_time_cursor(1, c2)
            self._time_cursors = {1: c1, 2: c2}
            self._cursor_readout.update_time_cursors(c1, c2)
        else:
            self._waveform.set_volt_cursor(0, c1)
            self._waveform.set_volt_cursor(1, c2)
            self._volt_cursors = {1: c1, 2: c2}
            self._push_volt_cursor_readout()

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
        old_offset = ch_state.offset

        # The rubberband coordinates are in display space where voltage
        # is scaled by _voltage_scale(ch).  Convert the selected voltage
        # range back to raw (scope-space) for V/div snapping.
        old_vscale = self._waveform._voltage_scale(ch)
        raw_volt_range = volt_range / old_vscale if old_vscale else volt_range

        # Snap T/div: smallest TDIV where full display >= selected range
        num_h = WaveformWidget.NUM_H_DIVS
        new_tdiv = TDIV_VALUES[-1]
        for tdiv in TDIV_VALUES:
            if num_h * tdiv >= time_range:
                new_tdiv = tdiv
                break

        # Snap V/div: smallest raw VDIV where full display >= selected range
        num_v = WaveformWidget.NUM_V_DIVS
        new_vdiv = VDIV_VALUES[-1]
        for vdiv in VDIV_VALUES:
            if num_v * vdiv >= raw_volt_range:
                new_vdiv = vdiv
                break

        # H position: center of selected time range
        new_h_pos = (t_min + t_max) / 2

        # V offset: convert display-space center back to raw voltage
        # offset so that the center of the selection maps to y = 0.
        center_y = (v_min + v_max) / 2
        new_offset = old_offset - center_y / old_vscale

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

        # Update waveform display (effective V/div = raw × probe)
        probe = self._channel_panel.get_state(ch).probe_factor
        effective = new_vdiv * probe
        self._waveform.set_channel_vdiv(ch, effective)
        self._waveform.set_scales(effective, new_tdiv)
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

        # Update waveform display (effective V/div = raw × probe)
        probe = self._channel_panel.get_state(ch).probe_factor
        effective = snap['vdiv'] * probe
        self._waveform.set_channel_vdiv(ch, effective)
        self._waveform.set_scales(effective, snap['tdiv'])
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
        ch = waveform.channel
        ch_state = self._channel_panel.get_state(ch)

        if self._dmm_mode:
            # Always auto-range (unless locked), even when held
            self._dmm_autorange(waveform)

            # Hold gate — skip DMM display update when held
            if self._hold_active:
                return

            # DMM path — feed data to DMM widget
            probe = waveform.probe_factor
            if ch_state.current_mode:
                # I = V × probe / R  →  pass effective factor as probe_factor
                effective_probe = probe / ch_state.shunt_resistance
            else:
                effective_probe = probe
            self._dmm_widget.update_waveform(
                ch, waveform.voltage,
                waveform.time_axis, effective_probe,
            )
            return

        # Oscilloscope path — update waveform display + measurements
        self._waveform.update_waveform(waveform)

        # Compute and display measurements.
        # Voltage data is in scope-space (no probe factor), so we scale
        # by the panel's authoritative probe_factor to get probe-tip voltage.
        # (The worker's waveform.probe_factor may be stale after session restore.)
        probe = ch_state.probe_factor
        if probe != 1.0:
            meas_voltage = waveform.voltage * probe
        else:
            meas_voltage = waveform.voltage

        # Convert to current if channel is in current mode
        if ch_state.current_mode and ch_state.shunt_resistance > 0:
            meas_voltage = meas_voltage / ch_state.shunt_resistance

        meas = measurements.compute_all(meas_voltage, waveform.time_axis)
        self._measurement_bar.update_measurements(ch, meas)

    def _recompute_channel_measurements(self, ch: int):
        """Recompute measurements for a channel using cached waveform data.

        Called when probe factor or current mode changes so measurements
        update immediately without waiting for the next acquisition frame.
        """
        wf = self._last_waveforms.get(ch)
        if wf is None:
            return
        ch_state = self._channel_panel.get_state(ch)
        probe = ch_state.probe_factor
        if probe != 1.0:
            meas_voltage = wf.voltage * probe
        else:
            meas_voltage = wf.voltage
        if ch_state.current_mode and ch_state.shunt_resistance > 0:
            meas_voltage = meas_voltage / ch_state.shunt_resistance
        meas = measurements.compute_all(meas_voltage, wf.time_axis)
        self._measurement_bar.update_measurements(ch, meas)

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

            # Set per-channel effective V/div for independent scaling
            v = ch_state.get("v_per_div", 1.0)
            probe = self._channel_panel.get_state(ch).probe_factor
            self._waveform.set_channel_vdiv(ch, v * probe)
            # Sync worker so WaveformData.probe_factor is correct
            self.sig_set_probe.emit(ch, probe)

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
            self._waveform.set_trigger_source_channel(src_ch)
            channels = state.get("channels", {})
            src_offset = channels.get(src_ch, {}).get("offset", 0.0)
            self._waveform.set_trigger_source_offset(src_offset)
        if "slope" in trig:
            self._trigger_panel.set_slope(trig["slope"])
            self._waveform.set_trigger_slope(trig["slope"])
        if "sweep" in trig:
            self._trigger_panel.set_sweep(trig["sweep"])
        if "coupling" in trig:
            self._trigger_panel.set_coupling(trig["coupling"])

        # Update waveform scale (effective V/div = raw × probe)
        active_ch = self._channel_panel._active_channel
        self._waveform.set_scales(
            self._effective_vdiv(active_ch),
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

    @Slot(str)
    def _on_trigger_status(self, status: str):
        """Update the trigger status indicator in the toolbar."""
        colors = {
            "ARMED": "#ffcc00",     # yellow — waiting for trigger
            "TRIG'D": "#50c878",    # green — trigger found
            "AUTO": "#ff8844",      # orange — auto-triggered (no edge found)
            "READY": "#888888",     # gray — idle
        }
        color = colors.get(status, "#888888")
        self._trigger_status_label.setText(f"  {status}  ")
        self._trigger_status_label.setStyleSheet(
            f"background-color: {color}; color: #000000; "
            f"border-radius: 4px; padding: 2px 8px; "
            f"{self._TB_FONT}"
        )

    # --- Connection ---

    def _show_connection_dialog(self):
        """Show the connection dialog."""
        last_port = self._settings.value("last_port", "")
        last_baud = self._settings.value("last_baud", 2000000, int)
        dialog = ConnectionDialog(
            last_port=last_port,
            last_baud=last_baud,
            parent=self,
        )
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

        # Save last port/baud for next launch
        if hasattr(bridge, "port"):
            self._settings.setValue("last_port", bridge.port)
        if hasattr(bridge, "baudrate"):
            self._settings.setValue("last_baud", bridge.baudrate)

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
        from gui.knob_widget import RotaryKnob

        # Gather current probe factors
        current_probes = {}
        for ch in range(1, NUM_CHANNELS + 1):
            current_probes[ch] = self._channel_panel.get_state(ch).probe_factor

        dialog = SettingsDialog(
            num_channels=NUM_CHANNELS,
            current_colors=self._channel_colors,
            current_probes=current_probes,
            knob_scroll_enabled=RotaryKnob._scroll_enabled,
            parent=self,
        )

        dialog.channel_color_changed.connect(self._on_color_changed)
        dialog.knob_scroll_changed.connect(RotaryKnob.set_scroll_enabled)

        if dialog.exec():
            # Apply probe settings — sync to worker, channel panel, and waveform
            probes = dialog.get_probe_factors()
            for ch, factor in probes.items():
                self.sig_set_probe.emit(ch, factor)
                self._channel_panel._states[ch].probe_factor = factor
                self._channel_panel._columns[ch].set_probe(factor)
                self._waveform.set_channel_probe(ch, factor)
                # Update per-channel effective V/div
                vdiv = self._channel_panel.get_state(ch).v_per_div
                self._waveform.set_channel_vdiv(ch, vdiv * factor)
                # Recompute measurements with updated probe factor
                self._recompute_channel_measurements(ch)
            # Refresh Y-axis with updated effective V/div
            active = self._channel_panel._active_channel
            self._waveform.set_scales(
                self._effective_vdiv(active),
                self._timebase_panel.t_per_div,
            )

    def _on_color_changed(self, ch: int, color: str):
        """Handle channel color change from settings."""
        self._channel_colors[ch] = color
        self._waveform.set_channel_color(ch, color)
        self._dmm_widget.set_channel_color(ch, color)

    def _show_probe_compensation(self):
        from gui.probe_comp_dialog import ProbeCompensationDialog
        dialog = ProbeCompensationDialog(self)
        dialog.exec()

    def _show_self_calibration(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, "Self-Calibration",
            "Self-calibration is not supported by the U2702A.\n\n"
            "The instrument does not expose calibration\n"
            "SCPI commands over the USBTMC interface.",
        )

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
            # Update per-channel effective V/div
            probe = self._channel_panel.get_state(ch).probe_factor
            self._waveform.set_channel_vdiv(ch, new_vdiv * probe)

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

        # Update waveform widget scaling (effective V/div = raw × probe)
        active_ch = self._channel_panel._active_channel
        tdiv = best_tdiv if best_tdiv else self._timebase_panel.t_per_div
        self._waveform.set_scales(self._effective_vdiv(active_ch), tdiv)

        self.statusBar().showMessage("Autoscale complete", 2000)

    # --- DMM auto-range ---

    def _dmm_autorange(self, waveform: WaveformData):
        """Auto-adjust V/div in DMM mode to keep signal well-framed.

        Throttled: only checks every 10 frames per channel.
        Adjusts when signal uses < 25% or > 90% of the current range.
        """
        if self._range_locked:
            return
        ch = waveform.channel
        count = self._dmm_ar_counter.get(ch, 0) + 1
        self._dmm_ar_counter[ch] = count

        if count % 10 != 0:
            return

        signal_vpp = measurements.vpp(waveform.voltage)
        if signal_vpp is None or signal_vpp < 1e-6:
            return

        ch_state = self._channel_panel.get_state(ch)
        current_vdiv = ch_state.v_per_div
        screen_range = WaveformWidget.NUM_V_DIVS * current_vdiv
        fill = signal_vpp / screen_range

        if fill < 0.25 or fill > 0.90:
            new_vdiv = pick_vdiv(signal_vpp, VDIV_VALUES)
            if new_vdiv != current_vdiv:
                self._channel_panel.set_channel_state(ch, v_per_div=new_vdiv)
                self.sig_set_vdiv.emit(ch, new_vdiv)
                probe = ch_state.probe_factor
                self._waveform.set_channel_vdiv(ch, new_vdiv * probe)
                if ch == self._channel_panel._active_channel:
                    self._waveform.set_scales(
                        new_vdiv * probe,
                        self._timebase_panel.t_per_div,
                    )

    # --- About ---

    def _show_about(self):
        """Show About/License dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    # --- QSettings persistence ---

    def _load_qsettings(self):
        """Load app-level settings from QSettings."""
        self._recent_files = self._settings.value("recent_files", [], list)
        # Clean out stale entries
        self._recent_files = [
            p for p in self._recent_files
            if isinstance(p, str) and p
        ][:5]

    def _save_qsettings(self):
        """Save app-level settings to QSettings."""
        self._settings.setValue("recent_files", self._recent_files[:5])
        # Window geometry
        geo = self.geometry()
        self._settings.setValue("window_geometry",
                                [geo.x(), geo.y(), geo.width(), geo.height()])
        # Last port + baud
        if self._bridge and hasattr(self._bridge, "port"):
            self._settings.setValue("last_port", self._bridge.port)
        if self._bridge and hasattr(self._bridge, "baudrate"):
            self._settings.setValue("last_baud", self._bridge.baudrate)

    def _add_recent_file(self, path: str):
        """Add a path to the recent files list (most recent first)."""
        # Remove duplicates
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:5]
        self._update_recent_files_menu()

    def _update_recent_files_menu(self):
        """Rebuild the Recent Sessions submenu."""
        self._recent_menu.clear()
        if not self._recent_files:
            empty = QAction("(none)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for path in self._recent_files:
            from pathlib import Path
            display = Path(path).name
            action = QAction(display, self)
            action.setToolTip(path)
            action.triggered.connect(
                lambda checked, p=path: self._load_session_from(p)
            )
            self._recent_menu.addAction(action)

    # --- Session file operations ---

    def _on_save_session(self):
        """Save to current path, or Save As if none."""
        if self._current_session_path:
            self._save_session_to(self._current_session_path)
        else:
            self._on_save_session_as()

    def _on_save_session_as(self):
        """Prompt user for a file path and save session."""
        from gui.session import SESSION_VERSION
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Session",
            "",
            "Session Files (*.json);;All Files (*)",
        )
        if path:
            if not path.endswith(".json"):
                path += ".json"
            self._save_session_to(path)

    def _on_load_session(self):
        """Prompt user to choose a session file and load it."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Session",
            "",
            "Session Files (*.json);;All Files (*)",
        )
        if path:
            self._load_session_from(path)

    def _on_reset_session(self):
        """Reset all settings to factory defaults."""
        from gui.session import default_state, apply_state

        # Stop acquisition if running
        if self._is_running:
            self._on_stop()

        # Switch back to scope mode if in DMM mode
        if self._dmm_mode:
            self._utility_panel.set_dmm_mode(False)

        apply_state(self, default_state(), restore_geometry=False)
        self._current_session_path = None
        self.statusBar().showMessage("Session reset to defaults", 3000)

    # --- Export handlers ---

    def _gather_export_context(self) -> dict:
        """Collect waveform data, measurements, and display state for export."""
        from gui.theme import NUM_CHANNELS
        waveforms = {}
        measurements = {}
        colors = {}
        channel_settings = {}
        for ch in range(1, NUM_CHANNELS + 1):
            wf = self._last_waveforms.get(ch)
            if wf is None:
                continue
            waveforms[ch] = wf
            measurements[ch] = self._measurement_bar._last_measurements.get(ch, {})
            colors[ch] = self._channel_colors.get(ch, "")
            st = self._channel_panel.get_state(ch)
            channel_settings[ch] = {
                "v_per_div": st.v_per_div,
                "offset": st.offset,
                "probe_factor": st.probe_factor,
                "current_mode": st.current_mode,
                "shunt_resistance": st.shunt_resistance,
            }
        trigger = {
            "level": self._trigger_panel.level,
            "source": self._trigger_panel.source,
            "slope": self._trigger_panel.slope,
        }
        # Convert cursor volt values to physical units for export labels
        # (display-space values are also passed for positioning on graph)
        raw_volt = list(self._waveform._volt_cursors)
        phys_v1 = self._cursor_display_to_physical(raw_volt[0])
        phys_v2 = self._cursor_display_to_physical(raw_volt[1])
        cursors = {
            "mode": self._waveform._cursor_mode,
            "time": list(self._waveform._time_cursors),
            "volt_display": raw_volt,       # display-space (for volt_to_y)
            "volt_physical": [phys_v1, phys_v2],  # physical (for labels)
            "channel": self._cursor_channel,
        }
        return {
            "waveforms": waveforms,
            "measurements": measurements,
            "colors": colors,
            "channel_settings": channel_settings,
            "trigger": trigger,
            "cursors": cursors,
            "enabled_measurements": self._measurement_bar.enabled_measurements,
        }

    def _on_export(self):
        """Open the unified export dialog (Data + Graph tabs)."""
        from gui.export_dialog import (
            ExportDialog, render_graph, save_graph,
        )
        from processing.export import export_csv, export_json, export_npz

        if not self._last_waveforms:
            self.statusBar().showMessage("No waveform data to export", 3000)
            return

        ctx = self._gather_export_context()

        dlg = ExportDialog(
            has_data=True,
            cursor_mode=self._waveform._cursor_mode,
            parent=self,
        )
        if dlg.exec() != ExportDialog.DialogCode.Accepted:
            return

        from pathlib import Path

        # Data export (CSV / JSON / NPZ)
        ds = dlg.data_settings
        if ds is not None:
            if ds.format == "csv":
                export_csv(ctx["waveforms"], ctx["measurements"], ds.path)
            elif ds.format == "npz":
                export_npz(ctx["waveforms"], ctx["measurements"], ds.path)
            else:
                export_json(ctx["waveforms"], ctx["measurements"], ds.path)
            self.statusBar().showMessage(
                f"Exported: {Path(ds.path).name}", 3000
            )
            return

        # Graph export (PNG / PDF)
        gs = dlg.graph_settings
        if gs is not None:
            img = render_graph(
                waveforms=ctx["waveforms"],
                measurements=ctx["measurements"],
                colors=ctx["colors"],
                trigger=ctx["trigger"],
                cursors=ctx["cursors"],
                channel_settings=ctx["channel_settings"],
                settings=gs,
                enabled_measurements=ctx["enabled_measurements"],
            )
            save_graph(img, gs)
            self.statusBar().showMessage(
                f"Exported: {Path(gs.path).name}", 3000
            )

    def _on_quick_export_csv(self):
        """Quick CSV export with file dialog (no export dialog)."""
        from processing.export import export_csv
        from datetime import datetime

        if not self._last_waveforms:
            self.statusBar().showMessage("No waveform data to export", 3000)
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"waveform_{ts}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name, "CSV Files (*.csv)"
        )
        if not path:
            return

        ctx = self._gather_export_context()
        export_csv(ctx["waveforms"], ctx["measurements"], path)

        from pathlib import Path
        self.statusBar().showMessage(
            f"Exported: {Path(path).name}", 3000
        )

    def _on_import(self):
        """Import waveform data from CSV, JSON, or NPZ file."""
        from pathlib import Path
        from processing.import_data import import_file
        from processing.waveform import WaveformData
        from processing import measurements
        import numpy as np
        import time

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Waveform Data", "",
            "All Supported (*.csv *.json *.npz);;"
            "CSV Files (*.csv);;JSON Files (*.json);;NumPy Archives (*.npz)"
        )
        if not path:
            return

        try:
            parsed = import_file(path)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Import Error", str(e))
            return

        time_axis = parsed["time_axis"]
        ch_data = parsed["channels"]

        if not ch_data:
            self.statusBar().showMessage("No channel data found in file", 3000)
            return

        # Stop acquisition if running
        if self._worker and self._worker._running:
            self._worker.stop()

        # Inject imported data into GUI
        from gui.theme import NUM_CHANNELS
        for ch in range(1, NUM_CHANNELS + 1):
            if ch not in ch_data:
                continue

            cd = ch_data[ch]
            voltage = cd["voltage"]
            raw_adc = cd.get("raw_adc")
            if raw_adc is None:
                raw_adc = np.zeros(len(voltage), dtype=np.uint8)

            wf = WaveformData(
                channel=ch,
                raw_adc=raw_adc,
                voltage=voltage,
                time_axis=time_axis[:len(voltage)],
                v_per_div=cd["v_per_div"],
                offset=cd["offset"],
                t_per_div=cd["t_per_div"],
                probe_factor=cd["probe_factor"],
                timestamp=time.monotonic(),
                trigger_sample=cd.get("trigger_sample"),
            )

            # Cache and display
            self._last_waveforms[ch] = wf

            # Update channel panel settings
            self._channel_panel.set_channel_state(
                ch,
                enabled=True,
                v_per_div=cd["v_per_div"],
                offset=cd["offset"],
                probe_factor=cd["probe_factor"],
            )

            # Enable channel on waveform widget (set_channel_state doesn't
            # emit channel_enabled signal, so we must sync manually)
            self._waveform.set_channel_enabled(ch, True)

            # Display waveform
            self._waveform.update_waveform(wf)

            # Compute measurements
            probe = cd["probe_factor"]
            meas_voltage = voltage * probe if probe != 1.0 else voltage
            meas = measurements.compute_all(meas_voltage, wf.time_axis)
            self._measurement_bar.update_measurements(ch, meas)

        # Disable channels not in the import
        for ch in range(1, NUM_CHANNELS + 1):
            if ch not in ch_data:
                self._channel_panel.set_channel_state(ch, enabled=False)
                self._waveform.set_channel_enabled(ch, False)

        # Update timebase from first channel
        first_ch = min(ch_data.keys())
        t_per_div = ch_data[first_ch]["t_per_div"]
        self._timebase_panel.set_tdiv(t_per_div)

        self.statusBar().showMessage(
            f"Imported: {Path(path).name} "
            f"({len(ch_data)} channel{'s' if len(ch_data) > 1 else ''})",
            5000,
        )

    def _save_session_to(self, path: str):
        """Gather state and write to a JSON file."""
        from gui.session import gather_state, save_to_file
        state = gather_state(self)
        save_to_file(state, path)
        self._current_session_path = path
        self._add_recent_file(path)
        from pathlib import Path
        self.statusBar().showMessage(
            f"Session saved: {Path(path).name}", 3000
        )

    def _load_session_from(self, path: str):
        """Load a session file and apply state."""
        from gui.session import load_from_file, apply_state
        state = load_from_file(path)
        if not state:
            self.statusBar().showMessage(
                f"Failed to load session: {path}", 3000
            )
            return
        apply_state(self, state)
        self._current_session_path = path
        self._add_recent_file(path)
        from pathlib import Path
        self.statusBar().showMessage(
            f"Session loaded: {Path(path).name}", 3000
        )

    def _auto_restore_session(self):
        """Restore last session on startup, then show connection dialog."""
        from gui.session import AUTO_SAVE_PATH, load_from_file, apply_state
        if AUTO_SAVE_PATH.exists():
            state = load_from_file(str(AUTO_SAVE_PATH))
            if state:
                apply_state(self, state)
        # Show connection dialog after restore
        self._show_connection_dialog()

    # --- Cleanup ---

    def closeEvent(self, event):
        """Auto-save session and clean shutdown."""
        # Auto-save current state
        from gui.session import gather_state, save_to_file, AUTO_SAVE_PATH
        try:
            state = gather_state(self)
            save_to_file(state, str(AUTO_SAVE_PATH))
        except Exception:
            pass  # Don't block exit on save failure

        # Save QSettings
        self._save_qsettings()

        if self._is_running:
            self.sig_stop.emit()

        if self._bridge:
            self._bridge.close()

        self._acq_thread.quit()
        self._acq_thread.wait(3000)

        super().closeEvent(event)
