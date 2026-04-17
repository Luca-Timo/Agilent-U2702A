"""
Generic instrument window — hosts any InstrumentDriver with any LayoutFactory.

This is the window the launcher spawns for non-scope instruments (DMMs
today; function generators / power supplies later). It owns:

  - one ``InstrumentDriver`` (already ``open()``-ed by the launcher)
  - one ``LayoutFactory`` (picks which panels to show)
  - its own ``QThread`` running a simple acquisition loop that calls
    ``driver.acquire()`` and dispatches the result to the layout

Multiple InstrumentWindows can coexist in the same Qt event loop —
each owns its own driver and thread, so the windows never race.

The scope still uses ``MainWindow`` for now because MainWindow's
signal wiring (channel panel → worker) is scope-specific and too
entangled to reuse byte-for-byte. That convergence is a future
refactor; for this commit the launcher picks which window class to
spawn based on the driver's capabilities.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QScrollArea, QSizePolicy,
)

from instrument.driver import InstrumentDriver
from instrument.serial_bridge import SerialBridgeError
from processing.acquisition_result import MeterReading

logger = logging.getLogger(__name__)


class _InstrumentAcquisitionWorker(QObject):
    """Minimal Qt-adapter around a non-scope driver.

    Scope uses the richer ``gui.acquisition_worker.AcquisitionWorker``
    (which still lives). For DMM/func-gen/PSU the acquisition model is
    simpler — one scalar reading per tick — so a small timer-driven
    worker is enough. Adds a per-driver thread and marshals results
    back to the main thread via Qt signals.
    """

    reading_ready = Signal(object)     # MeterReading / GeneratorState / ...
    error_occurred = Signal(str)

    def __init__(self, driver: InstrumentDriver, poll_ms: int = 250):
        super().__init__()
        self._driver = driver
        self._poll_ms = poll_ms
        self._running = False
        self._timer: Optional[QTimer] = None

    @Slot()
    def start(self):
        # QTimer lives on the worker's thread; started via queued slot
        # delivery so it's created in the right thread context.
        self._timer = QTimer()
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._tick)
        self._running = True
        self._timer.start()

    @Slot()
    def stop(self):
        self._running = False
        if self._timer is not None:
            self._timer.stop()

    def _tick(self):
        if not self._running:
            return
        try:
            result = self._driver.acquire()
        except SerialBridgeError as e:
            logger.warning("Acquisition error: %s", e)
            self.error_occurred.emit(str(e))
            return
        if result is not None:
            self.reading_ready.emit(result)


class InstrumentWindow(QMainWindow):
    """Top-level window for a single connected instrument.

    Args:
        driver: an already-open ``InstrumentDriver``. The window takes
            ownership — closing the window closes the driver and its
            acquisition thread.
        layout: a ``LayoutFactory`` (e.g. ``DMMLayout``) describing
            which widgets to show.
        title: window title. Defaults to ``driver.capabilities.kind``
            plus the driver's bridge port.
    """

    # Poll intervals (ms). Scalar instruments don't need 30 fps; the
    # UI renders fine at ~4 Hz for a DMM.
    POLL_MS_BY_KIND = {
        "scalar":   250,   # DMM
        "setpoint": 500,   # func-gen / PSU readback
        "waveform": 50,    # (reserved — scope uses MainWindow)
    }

    def __init__(self, driver: InstrumentDriver, layout,
                 title: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._driver = driver
        self._layout_factory = layout

        caps = driver.capabilities
        if title is None:
            port = getattr(driver.bridge, "port", "unknown")
            title = f"{caps.kind.value if hasattr(caps.kind, 'value') else caps.kind}  —  {port}"
        self.setWindowTitle(title)
        self.resize(960, 640)

        self._build_ui()
        self._build_menu()
        self._spawn_worker()

    # -- UI -----------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left column: displays from the layout
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 0, 0)
        left_v.setSpacing(4)
        for spec in self._layout_factory.display_widgets():
            setattr(self, spec.attr, spec.widget)
            if spec.hidden:
                spec.widget.setVisible(False)
            left_v.addWidget(spec.widget, stretch=spec.stretch)
        splitter.addWidget(left)

        # Right column: control panels (if any). Scrollable for
        # consistency with MainWindow. DMMLayout currently returns
        # an empty list, so we hide the right column entirely.
        controls = list(self._layout_factory.control_panels())
        if controls:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            host = QWidget()
            host_v = QVBoxLayout(host)
            host_v.setContentsMargins(4, 0, 4, 0)
            host_v.setSpacing(6)
            for spec in controls:
                setattr(self, spec.attr, spec.widget)
                if spec.hidden:
                    spec.widget.setVisible(False)
                host_v.addWidget(spec.widget, stretch=spec.stretch)
            host_v.addStretch()
            scroll.setWidget(host)
            splitter.addWidget(scroll)
            splitter.setSizes([700, 300])
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)

        root.addWidget(splitter, stretch=1)
        self.setCentralWidget(central)

        self.statusBar().showMessage(
            f"Connected — {self._driver.capabilities.kind}",
        )

    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        close_action = QAction("&Close Window", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

    # -- Acquisition thread ------------------------------------------

    def _spawn_worker(self):
        caps = self._driver.capabilities
        # ``kind`` is an Enum whose .value is "scope"/"dmm"/... but the
        # poll interval lookup below uses the acquisition model name
        # ("scalar" / "setpoint" / "waveform") which is the right axis.
        model = caps.acquisition_model
        model_key = model.value if hasattr(model, "value") else str(model)
        poll_ms = self.POLL_MS_BY_KIND.get(model_key, 250)

        self._worker_thread = QThread(self)
        self._worker = _InstrumentAcquisitionWorker(self._driver, poll_ms=poll_ms)
        self._worker.moveToThread(self._worker_thread)

        self._worker.reading_ready.connect(self._on_reading_ready)
        self._worker.error_occurred.connect(self._on_worker_error)

        # Kick the worker once the thread's event loop is running.
        self._worker_thread.started.connect(self._worker.start)
        self._worker_thread.start()

    @Slot(object)
    def _on_reading_ready(self, result):
        """Route an acquisition result to the right display widget.

        Today handles MeterReading → DMMWidget. Add more branches
        when func-gen / PSU / eload results show up.
        """
        if isinstance(result, MeterReading):
            dmm_widget = getattr(self, "_dmm_widget", None)
            if dmm_widget is None:
                return
            # DMMWidget expects a DMMReading; adapt MeterReading.
            self._push_to_dmm_widget(dmm_widget, result)

    def _push_to_dmm_widget(self, dmm_widget, reading: MeterReading):
        """Adapt MeterReading → the shape DMMWidget accepts."""
        # DMMWidget.update_reading(channel, primary, min, max, avg, freq, mode)
        # — signature may vary; we fall back to setting card values directly
        # if a simple push method isn't available.
        if hasattr(dmm_widget, "update_reading"):
            dmm_widget.update_reading(
                channel=reading.channel,
                value=reading.primary,
                minimum=reading.minimum,
                maximum=reading.maximum,
                average=reading.average,
                unit=reading.unit,
            )
            return
        # Fallback: hit the channel card directly.
        cards = getattr(dmm_widget, "_channel_cards", {})
        card = cards.get(reading.channel)
        if card is None:
            return
        for method, value in (
            ("set_value", reading.primary),
            ("set_unit", reading.unit),
            ("set_min", reading.minimum),
            ("set_max", reading.maximum),
            ("set_avg", reading.average),
            ("set_samples", reading.samples),
        ):
            if hasattr(card, method) and value is not None:
                getattr(card, method)(value)

    @Slot(str)
    def _on_worker_error(self, msg: str):
        self.statusBar().showMessage(f"Error: {msg}", 5000)

    # -- Lifecycle ---------------------------------------------------

    def closeEvent(self, event):
        # Stop the worker, close the driver, tear down the thread.
        try:
            self._worker.stop()
        except Exception:
            pass
        self._worker_thread.quit()
        if not self._worker_thread.wait(2000):
            logger.warning("Instrument worker thread did not exit cleanly")
            self._worker_thread.terminate()
            self._worker_thread.wait(1000)
        try:
            self._driver.close()
        except Exception as e:
            logger.warning("Driver close on exit failed: %s", e)
        self._worker.deleteLater()
        super().closeEvent(event)
