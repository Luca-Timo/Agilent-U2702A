"""
LauncherWindow — the lab-bench app's top-level entry point.

Replaces the old "open MainWindow directly" startup flow. Shows two
sections to the user:

  1. **Detected instruments** — ports that answered ``*IDN?`` (via
     ``instrument.discovery.discover``) together with their registry
     match when available. Hidden if auto-discovery is disabled in
     Settings.

  2. **Demo mode** — one entry per model in the config registry, so
     the user can always spin up a synthetic instrument regardless of
     what's physically connected. Fulfils the explicit request that
     every available device type is reachable from the launcher in
     demo mode.

Clicking **Open** in either section spawns a dedicated window for
that instrument (scope → ``MainWindow``; DMM / others → ``InstrumentWindow``).
Multiple windows can be open at once — the launcher is just a manager.

Closing the launcher quits the app; if there are open instrument
windows, the user is asked first.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFrame, QSizePolicy, QMessageBox,
)

from config import (
    ACTIVE, REGISTRY,
    DMMConfig, FunctionGeneratorConfig, OscilloscopeConfig,
)
from gui.app_settings import SETTINGS
from gui.instrument_window import InstrumentWindow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Device row widget — one entry in either section
# ---------------------------------------------------------------------


class _DeviceRow(QFrame):
    """One device in the launcher list. Emits ``open_requested``
    carrying the model name and the port (or None for demo)."""

    open_requested = Signal(str, object, bool)   # model, port|None, demo

    def __init__(self, *, title: str, subtitle: str,
                 model: str, port: Optional[str],
                 demo: bool, enabled: bool = True, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "_DeviceRow { border: 1px solid #3a3a3a; border-radius: 6px; "
            "background-color: #202020; padding: 8px; }"
            "_DeviceRow:hover { border-color: #4a9eff; }"
        )
        self._model = model
        self._port = port
        self._demo = demo

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)

        title_lbl = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        text_box.addWidget(title_lbl)

        if subtitle:
            subtitle_lbl = QLabel(subtitle)
            subtitle_lbl.setStyleSheet("color: #888888; font-size: 11px;")
            text_box.addWidget(subtitle_lbl)

        layout.addLayout(text_box, stretch=1)

        self._open_btn = QPushButton("Open")
        self._open_btn.setFixedWidth(100)
        self._open_btn.setEnabled(enabled)
        self._open_btn.clicked.connect(self._on_open_clicked)
        layout.addWidget(self._open_btn)

    def _on_open_clicked(self):
        self.open_requested.emit(self._model, self._port, self._demo)


# ---------------------------------------------------------------------
# LauncherWindow
# ---------------------------------------------------------------------


class LauncherWindow(QMainWindow):
    """Device picker + window manager. Top-level of the app."""

    WINDOW_TITLE = "Lab Bench — Launcher"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.WINDOW_TITLE)
        self.resize(640, 580)
        self._child_windows: list[QMainWindow] = []
        self._build_ui()
        self._build_menu()
        self.refresh()

    # -- UI ----------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Header
        header = QLabel("Lab Bench")
        header_font = QFont()
        header_font.setPointSize(18)
        header_font.setBold(True)
        header.setFont(header_font)
        root.addWidget(header)

        subtitle = QLabel(
            "Open any connected instrument, or a demo session for any "
            "registered model. Multiple windows can be open at once."
        )
        subtitle.setStyleSheet("color: #888888;")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # Controls row (refresh + settings hint)
        ctrl_row = QHBoxLayout()
        self._refresh_btn = QPushButton("⟳  Refresh")
        self._refresh_btn.setFixedWidth(110)
        self._refresh_btn.clicked.connect(self.refresh)
        ctrl_row.addWidget(self._refresh_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888888; padding-left: 8px;")
        ctrl_row.addWidget(self._status_lbl, stretch=1)
        root.addLayout(ctrl_row)

        # Scrollable device list (detected + demo sections live here)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #333333; border-radius: 6px; "
            "background: #161616; }"
        )
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(12, 12, 12, 12)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_host)
        root.addWidget(scroll, stretch=1)

        self.setCentralWidget(central)

        self.statusBar().showMessage("Ready")

    def _build_menu(self):
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        refresh_action = QAction("&Refresh Devices", self)
        refresh_action.setShortcut("Ctrl+R")
        refresh_action.triggered.connect(self.refresh)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        settings_menu = bar.addMenu("&Settings")
        prefs_action = QAction("&Preferences…", self)
        prefs_action.triggered.connect(self._open_settings)
        settings_menu.addAction(prefs_action)

        help_menu = bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # -- Device list -------------------------------------------------

    def refresh(self):
        """Repopulate the device list.

        Probes ports via ``*IDN?`` when auto-discovery is enabled;
        otherwise just shows the demo section.
        """
        # Clear existing rows (everything except the trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._add_detected_section()
        self._add_demo_section()

        self._update_status_line()

    def _add_detected_section(self):
        """Top section — real instruments found on the bench."""
        if not SETTINGS.auto_discovery_enabled:
            header = self._section_header(
                "Detected instruments",
                "(auto-discovery disabled in Settings)",
            )
            self._insert_at_top(header)
            return

        header = self._section_header(
            "Detected instruments",
            "Ports that responded to *IDN?",
        )
        self._insert_at_top(header)

        # Local import so the launcher loads fast even before any
        # serial-port probing is needed.
        from instrument.discovery import discover
        self.statusBar().showMessage("Scanning serial ports…")
        try:
            discovered = discover()
        except Exception as e:
            logger.warning("Discovery failed: %s", e)
            discovered = []
        self.statusBar().showMessage("Ready")

        if not discovered:
            empty = QLabel("  No instruments detected.")
            empty.setStyleSheet("color: #666666; padding: 4px 0;")
            self._insert_at_top(empty)
            return

        for inst in discovered:
            matched = inst.is_matched
            title = inst.display_name
            if inst.raw_idn:
                subtitle = f"IDN: {inst.raw_idn}"
            else:
                subtitle = "No response"
            row = _DeviceRow(
                title=title,
                subtitle=subtitle,
                model=inst.model if inst.model else "",
                port=inst.port,
                demo=False,
                enabled=bool(matched),
            )
            if not matched:
                row._open_btn.setToolTip(
                    "Instrument model not in the config registry — "
                    "add a preset in config/presets/ to enable."
                )
            row.open_requested.connect(self._open_device)
            self._insert_at_top(row)

    def _add_demo_section(self):
        """Bottom section — demo mode for every registered model.

        Always present, regardless of what's physically connected.
        """
        header = self._section_header(
            "Demo mode",
            "Synthetic instruments — no hardware required",
        )
        self._insert_at_top(header)

        # Registry iteration order = dict insertion order (3.7+).
        for model_name, cfg in REGISTRY.items():
            row = _DeviceRow(
                title=f"{cfg.display_name} (demo)",
                subtitle=self._config_subtitle(cfg),
                model=model_name,
                port=None,
                demo=True,
            )
            row.open_requested.connect(self._open_device)
            self._insert_at_top(row)

    def _section_header(self, title: str, subtitle: str) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(0)
        t = QLabel(title)
        t_font = QFont()
        t_font.setPointSize(11)
        t_font.setBold(True)
        t.setFont(t_font)
        t.setStyleSheet("color: #b0b0b0;")
        v.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet("color: #666666; font-size: 10px;")
            v.addWidget(s)
        return box

    def _insert_at_top(self, widget: QWidget) -> None:
        # Insert before the trailing stretch (which is always at the
        # last index). Walking backwards keeps visual order consistent
        # since each section is added once and grows downward.
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    def _config_subtitle(self, cfg) -> str:
        if isinstance(cfg, OscilloscopeConfig):
            return (
                f"Oscilloscope · {cfg.num_channels} ch · "
                f"{cfg.adc.data_length} samples @ "
                f"{cfg.grid.vertical_divs}×{cfg.grid.horizontal_divs} grid"
            )
        if isinstance(cfg, DMMConfig):
            return (
                f"Multimeter · {cfg.display_digits}-digit · "
                f"{len(cfg.measurement_modes)} measurement modes"
            )
        return cfg.__class__.__name__

    # -- Opening windows ---------------------------------------------

    def _open_device(self, model: str, port, demo: bool):
        """Instantiate a driver via LabSession rules and spawn a window."""
        from automation.session import DRIVER_REGISTRY
        from config import REGISTRY
        from instrument.demo_bridge import DemoBridge
        from instrument.demo_dmm_bridge import DemoDMMBridge
        from instrument.serial_bridge import SerialBridge

        if model not in DRIVER_REGISTRY or model not in REGISTRY:
            QMessageBox.warning(
                self, "Unsupported",
                f"No driver registered for model {model!r}.",
            )
            return

        cfg = REGISTRY[model]
        driver_cls = DRIVER_REGISTRY[model]

        # Pick the bridge — mirrors LabSession._build_bridge.
        try:
            if demo:
                if isinstance(cfg, DMMConfig):
                    bridge = DemoDMMBridge(model=model)
                else:
                    bridge = DemoBridge()
            else:
                bridge = SerialBridge(
                    port=port,
                    baudrate=cfg.serial.baudrate,
                    timeout=cfg.serial.timeout_s,
                )
            driver = driver_cls(bridge)
            driver.open()
        except Exception as e:
            logger.exception("Failed to open %s", model)
            QMessageBox.critical(
                self, "Open failed",
                f"Could not open {model}:\n\n{e}",
            )
            return

        # Choose the right window class for this instrument kind.
        window = self._spawn_window(driver, cfg, demo=demo, port=port)
        window.destroyed.connect(lambda _=None, w=window: self._on_child_destroyed(w))
        self._child_windows.append(window)
        window.show()
        self._update_status_line()

    def _spawn_window(self, driver, cfg, *, demo: bool, port) -> QMainWindow:
        """Pick MainWindow for scopes, InstrumentWindow for everything else.

        Scope keeps its rich MainWindow UI (trigger panel, measurement
        bar, FFT, math, export, session save/restore) via the
        ``bridge=`` kwarg that skips the connection dialog.

        DMM / func-gen / PSU use the layout-driven ``InstrumentWindow``.
        """
        kind = cfg.__class__.__name__

        if isinstance(cfg, OscilloscopeConfig):
            from gui.main_window import MainWindow
            title_suffix = "(demo)" if demo else (port or "")
            win = MainWindow(preopened_bridge=driver.bridge)
            win.setWindowTitle(f"{cfg.display_name}  {title_suffix}".strip())
            return win

        if isinstance(cfg, DMMConfig):
            from gui.layouts import DMMLayout
            layout = DMMLayout(num_channels=cfg.num_channels)
            title_suffix = "(demo)" if demo else (port or "")
            return InstrumentWindow(
                driver=driver,
                layout=layout,
                title=f"{cfg.display_name}  {title_suffix}".strip(),
            )

        if isinstance(cfg, FunctionGeneratorConfig):
            from gui.layouts import FunctionGeneratorLayout
            layout = FunctionGeneratorLayout(
                frequency_range=cfg.frequency_range,
                amplitude_range=cfg.amplitude_range,
            )
            title_suffix = "(demo)" if demo else (port or "")
            return InstrumentWindow(
                driver=driver,
                layout=layout,
                title=f"{cfg.display_name}  {title_suffix}".strip(),
            )

        # Fallback: raise so we notice missing coverage instead of
        # silently producing an empty window.
        raise RuntimeError(
            f"No window class wired for config type {kind}; "
            f"add a branch to LauncherWindow._spawn_window.",
        )

    def _on_child_destroyed(self, window):
        if window in self._child_windows:
            self._child_windows.remove(window)
        self._update_status_line()

    def _update_status_line(self):
        n = len(self._child_windows)
        self._status_lbl.setText(
            f"{n} window{'s' if n != 1 else ''} open"
            if n > 0 else "Ready"
        )

    # -- Menu actions ------------------------------------------------

    def _open_settings(self):
        from gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(parent=self)
        dlg.exec()
        # Discovery toggle may have changed — rescan.
        self.refresh()

    def _show_about(self):
        QMessageBox.about(
            self, "Lab Bench",
            "<h3>Lab Bench</h3>"
            f"<p>Version {getattr(ACTIVE, 'model', '')}</p>"
            "<p>Cross-instrument bench app — oscilloscopes, DMMs, "
            "function generators.</p>"
            "<p>Launch multiple instruments from one window.</p>"
        )

    # -- Lifecycle ---------------------------------------------------

    def closeEvent(self, event):
        if self._child_windows:
            reply = QMessageBox.question(
                self, "Quit Lab Bench?",
                f"There {'are' if len(self._child_windows) != 1 else 'is'} "
                f"{len(self._child_windows)} instrument "
                f"window{'s' if len(self._child_windows) != 1 else ''} "
                "still open. Close them all and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # Close child windows first; they'll run their own cleanup.
            for w in list(self._child_windows):
                w.close()
        super().closeEvent(event)
