"""
Acquisition worker — thin Qt adapter around a headless InstrumentDriver.

Owns:
  - The QThread lifecycle and acquisition loop.
  - The run/mode flags (guarded by QMutex so the GUI thread's ``stop()``
    slot can preempt a live acquisition cleanly).
  - FPS counting and ``trigger_status`` / ``error_occurred`` signals.

Does NOT own:
  - SCPI command strings, channel settings, ADC parsing. All that lives
    in ``instrument.drivers.u2702a.U2702ADriver`` and is called
    synchronously from this worker. Scripts bypass the worker and call
    the driver directly.

The Qt signal/slot surface (``sig_set_vdiv``, ``waveform_ready``, etc.)
is unchanged — ``MainWindow`` doesn't need to know a driver exists.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from PySide6.QtCore import (
    QCoreApplication,
    QMutex,
    QMutexLocker,
    QObject,
    QThread,
    Signal,
    Slot,
)

from instrument.drivers.u2702a import ChannelSettings, U2702ADriver
from instrument.driver import Bridge
from instrument.serial_bridge import SerialBridgeError

logger = logging.getLogger(__name__)


class AcquisitionWorker(QObject):
    """Qt wrapper around ``U2702ADriver``.

    Signals:
        waveform_ready(WaveformData) — new waveform data for a channel
        init_complete(dict)          — instrument init sequence complete
        status_changed(str)          — bridge status change
        error_occurred(str)          — error message
        fps_update(float)            — current frames-per-second
        trigger_status(str)          — ARMED, TRIG'D, AUTO, READY
    """

    waveform_ready = Signal(object)
    init_complete = Signal(dict)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    fps_update = Signal(float)
    trigger_status = Signal(str)

    def __init__(self):
        super().__init__()
        self._driver: Optional[U2702ADriver] = None

        # Lock guards only the loop-control flags that the GUI thread
        # writes via @Slot. Settings state is owned by the driver's own
        # ``threading.Lock``.
        self._state_lock = QMutex()
        self._running = False
        self._mode = "stopped"  # "stopped" | "continuous" | "single"

        self._frame_count = 0
        self._fps_timer = 0.0

    # -- Driver / bridge hookup --------------------------------------

    @property
    def bridge(self) -> Optional[Bridge]:
        return self._driver.bridge if self._driver else None

    @property
    def driver(self) -> Optional[U2702ADriver]:
        return self._driver

    @Slot(object)
    def set_bridge(self, bridge: Bridge):
        """Bind to a freshly-connected bridge (from the connection dialog)."""
        self._driver = U2702ADriver(bridge) if bridge is not None else None
        if bridge and bridge.is_open:
            self.status_changed.emit(bridge.bridge_status)

    # -- Loop-flag helpers -------------------------------------------

    def _is_running(self) -> bool:
        with QMutexLocker(self._state_lock):
            return self._running

    def _mode_is(self, mode: str) -> bool:
        with QMutexLocker(self._state_lock):
            return self._mode == mode

    # -- Init sequence -----------------------------------------------

    @Slot()
    def run_init_sequence(self):
        """Run the instrument init sequence and emit parsed state."""
        if self._driver is None or not self._driver.bridge.is_open:
            self.error_occurred.emit("Not connected")
            return
        try:
            parsed = self._driver.init_sequence()
            self.init_complete.emit(parsed)
        except SerialBridgeError as e:
            logger.warning("Init failed: %s", e)
            self.error_occurred.emit(f"Init failed: {e}")

    # -- Guarded setter helper ---------------------------------------

    def _guarded(self, method_name: str, *args, label: str):
        """Call a driver method; emit + log on SCPI failure."""
        if self._driver is None:
            return
        try:
            getattr(self._driver, method_name)(*args)
        except SerialBridgeError as e:
            logger.warning("%s failed: %s", label, e)
            self.error_occurred.emit(f"{label} failed: {e}")

    # -- Channel settings (GUI slots) --------------------------------

    @Slot(int, bool)
    def set_channel_enabled(self, ch: int, enabled: bool):
        if self._driver is not None:
            self._driver.set_channel_enabled(ch, enabled)

    @Slot(int, float)
    def set_vdiv(self, ch: int, value: float):
        self._guarded("set_vdiv", ch, value, label=f"CH{ch} V/div")

    @Slot(int, float)
    def set_offset(self, ch: int, value: float):
        self._guarded("set_offset", ch, value, label=f"CH{ch} offset")

    @Slot(int, str)
    def set_coupling(self, ch: int, coupling: str):
        self._guarded("set_coupling", ch, coupling, label=f"CH{ch} coupling")

    @Slot(int, bool)
    def set_bwlimit(self, ch: int, enabled: bool):
        self._guarded("set_bwlimit", ch, enabled, label=f"CH{ch} BW limit")

    @Slot(int, float)
    def set_probe(self, ch: int, factor: float):
        if self._driver is not None:
            self._driver.set_probe(ch, factor)

    @Slot(float)
    def set_tdiv(self, value: float):
        self._guarded("set_tdiv", value, label="T/div")

    @Slot(float)
    def set_position(self, value: float):
        self._guarded("set_position", value, label="T position")

    @Slot(float)
    def set_trigger_level(self, value: float):
        self._guarded("set_trigger_level", value, label="Trigger level")

    @Slot(str)
    def set_trigger_source(self, source: str):
        self._guarded("set_trigger_source", source, label="Trigger source")

    @Slot(str)
    def set_trigger_slope(self, slope: str):
        self._guarded("set_trigger_slope", slope, label="Trigger slope")

    @Slot(str)
    def set_trigger_sweep(self, mode: str):
        self._guarded("set_trigger_sweep", mode, label="Trigger sweep")

    @Slot(str)
    def set_trigger_coupling(self, coupling: str):
        self._guarded("set_trigger_coupling", coupling, label="Trigger coupling")

    # -- Acquisition control -----------------------------------------

    @Slot()
    def start_continuous(self):
        with QMutexLocker(self._state_lock):
            self._mode = "continuous"
            self._running = True
        self._frame_count = 0
        self._fps_timer = time.monotonic()
        self._acquisition_loop()

    @Slot()
    def start_single(self):
        with QMutexLocker(self._state_lock):
            self._mode = "single"
            self._running = True
        try:
            self._acquire_once()
        finally:
            with QMutexLocker(self._state_lock):
                self._running = False
                self._mode = "stopped"

    @Slot()
    def stop(self):
        with QMutexLocker(self._state_lock):
            self._running = False
            self._mode = "stopped"
        self.trigger_status.emit("READY")

    def _acquisition_loop(self):
        while self._is_running() and self._mode_is("continuous"):
            self._acquire_once()

            self._frame_count += 1
            elapsed = time.monotonic() - self._fps_timer
            if elapsed >= 1.0:
                fps = self._frame_count / elapsed
                self.fps_update.emit(fps)
                self._frame_count = 0
                self._fps_timer = time.monotonic()

            # Let queued slot deliveries (stop(), set_vdiv(), etc.) run.
            QCoreApplication.processEvents()
            QThread.msleep(1)

    def _acquire_once(self):
        if self._driver is None or not self._driver.bridge.is_open:
            self.error_occurred.emit("Not connected")
            self.stop()
            return

        self.trigger_status.emit("ARMED")
        try:
            result = self._driver.acquire(should_continue=self._is_running)
        except SerialBridgeError as e:
            logger.warning("Acquisition failed: %s", e)
            self.error_occurred.emit(f"Acquisition failed: {e}")
            return

        self.trigger_status.emit("TRIG'D" if result.trigger_found else "AUTO")
        for wf in result.waveforms:
            self.waveform_ready.emit(wf)
