"""
Agilent 33120A function/arbitrary waveform generator driver.

Implements the ``InstrumentDriver`` protocol with no Qt dependency —
same entry points used by GUI panels and by automation scripts.

MVP scope (per the v0.11 plan): frequency, amplitude, DC offset,
waveform shape (SIN/SQU/TRI/RAMP/NOIS/DC), phase, square-wave duty
cycle, output enable, output load termination. Modulation / sweep /
burst / arb upload land in follow-ups as additional setpoint groups.

Safety invariant: ``open()`` always ends with the output OFF. This
is enforced here (not in the UI) so the same guarantee holds for
scripts, tests, and future callers. If a future consumer needs to
preserve the hardware's previous output state, it can pass
``restore_output=True`` — not exposed publicly today.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from typing import Any, Optional

from config import FunctionGeneratorConfig
from instrument.capabilities import Capabilities, FUNCGEN_DEFAULTS
from instrument.driver import Bridge
from instrument.serial_bridge import SerialBridgeError
from processing.acquisition_result import GeneratorState

logger = logging.getLogger(__name__)


# Waveform shapes the 33120A supports. Keys match FUNC:SHAP SCPI values.
_VALID_WAVEFORMS = ("SIN", "SQU", "TRI", "RAMP", "NOIS", "DC")

# Output load: either "50" (ohms) or "INF" (high-impedance). The 33120A
# uses this to correct the displayed amplitude — the actual hardware
# output impedance is always 50 Ω.
_VALID_LOADS = ("50", "INF")


class Agilent33120ADriver:
    """Concrete ``InstrumentDriver`` for the Agilent 33120A.

    All methods are synchronous and thread-safe via a private lock.
    GUI calls via the Qt worker thread; scripts call directly.
    """

    def __init__(self, bridge: Bridge,
                 config: Optional[FunctionGeneratorConfig] = None):
        self.bridge = bridge
        self._config = config

        # Capabilities come from the shared defaults plus the config's
        # channel count (33120A is 1-channel; future multi-channel
        # models reuse this class path via a subclass).
        caps = FUNCGEN_DEFAULTS
        if config is not None:
            caps = replace(caps, num_channels=config.num_channels)
        self.capabilities: Capabilities = caps

        # Cached setpoints — the UI consults these on every knob change
        # and the acquire() loop refreshes them from the instrument.
        self._lock = threading.Lock()
        self._frequency: float = 1000.0
        self._amplitude: float = 0.1
        self._offset: float = 0.0
        self._phase: float = 0.0
        self._waveform: str = "SIN"
        self._duty_cycle: float = 50.0         # % (SQU only)
        self._output_enabled: bool = False
        self._output_load: str = "50"

    # -- Lifecycle ---------------------------------------------------

    def open(self) -> None:
        """Open the bridge and enforce the output-off safety invariant.

        Sends ``OUTP OFF`` immediately; nothing else is changed on the
        instrument so a user's manually-set frequency / waveform survives
        a reconnect. Callers wanting a clean slate should do ``*RST``
        through ``apply_setting`` afterwards (not yet exposed — add if
        it becomes useful).
        """
        if not self.bridge.is_open:
            self.bridge.open()
        try:
            self.bridge.write("OUTP OFF", timeout=2.0)
        except SerialBridgeError as e:
            # Driver open() must succeed even if the instrument doesn't
            # respond — the UI will surface the error on the next
            # operation. Log and continue.
            logger.warning("OUTP OFF on open() failed: %s", e)
        with self._lock:
            self._output_enabled = False

    def close(self) -> None:
        if self.bridge and self.bridge.is_open:
            # Defensive: turn output off again on disconnect so nothing
            # is live after the driver goes away.
            try:
                self.bridge.write("OUTP OFF", timeout=1.0)
            except SerialBridgeError:
                pass
            self.bridge.close()

    def init_sequence(self) -> dict:
        """Probe IDN + read back current setpoints into the cache."""
        idn = ""
        try:
            idn = self.bridge.query("*IDN?", timeout=1.5).strip()
        except SerialBridgeError as e:
            logger.warning("*IDN? failed during init: %s", e)

        # Populate cached setpoints from the instrument so the UI
        # reflects whatever the 33120A is currently configured for
        # (minus the output, which was forced off by open()).
        self._refresh_from_instrument()

        with self._lock:
            return {
                "idn": idn,
                "frequency": self._frequency,
                "amplitude": self._amplitude,
                "offset": self._offset,
                "phase": self._phase,
                "waveform": self._waveform,
                "output_enabled": self._output_enabled,
                "output_load": self._output_load,
            }

    def _refresh_from_instrument(self) -> None:
        """Read every setpoint from the instrument into the cache.

        Called on init and on every ``acquire()``. Silently skips any
        query the instrument doesn't answer — callers can still drive
        a partially-responsive DMM.
        """
        try:
            freq = float(self.bridge.query("FREQ?", timeout=1.5))
        except (SerialBridgeError, ValueError):
            freq = None
        try:
            amp = float(self.bridge.query("VOLT?", timeout=1.5))
        except (SerialBridgeError, ValueError):
            amp = None
        try:
            off = float(self.bridge.query("VOLT:OFFS?", timeout=1.5))
        except (SerialBridgeError, ValueError):
            off = None
        try:
            phase = float(self.bridge.query("PHAS?", timeout=1.5))
        except (SerialBridgeError, ValueError):
            phase = None
        try:
            shape = self.bridge.query("FUNC:SHAP?", timeout=1.5).strip().upper()
        except SerialBridgeError:
            shape = None
        try:
            out_raw = self.bridge.query("OUTP?", timeout=1.5).strip()
            out_enabled = out_raw in ("1", "ON")
        except SerialBridgeError:
            out_enabled = None
        try:
            load = self.bridge.query("OUTP:LOAD?", timeout=1.5).strip().upper()
            # 33120A returns either "50" or "INF" (sometimes as "+5.000000E+01").
            # Normalise common variants.
            if load not in _VALID_LOADS:
                try:
                    load = "50" if abs(float(load) - 50.0) < 1e-3 else "INF"
                except ValueError:
                    load = None
        except SerialBridgeError:
            load = None

        with self._lock:
            if freq is not None:
                self._frequency = freq
            if amp is not None:
                self._amplitude = amp
            if off is not None:
                self._offset = off
            if phase is not None:
                self._phase = phase
            if shape is not None and shape in _VALID_WAVEFORMS:
                self._waveform = shape
            if out_enabled is not None:
                self._output_enabled = out_enabled
            if load in _VALID_LOADS:
                self._output_load = load

    # -- Typed setters ------------------------------------------------

    def set_frequency(self, hz: float) -> None:
        self._check_range("frequency", hz,
                          lo=(self._config.frequency_range[0]
                              if self._config else 0.1),
                          hi=(self._config.frequency_range[1]
                              if self._config else 15e6))
        self.bridge.write(f"FREQ {hz:.6E}", timeout=2.0)
        with self._lock:
            self._frequency = float(hz)

    def set_amplitude(self, vpp: float) -> None:
        self._check_range("amplitude", vpp,
                          lo=(self._config.amplitude_range[0]
                              if self._config else 0.05),
                          hi=(self._config.amplitude_range[1]
                              if self._config else 10.0))
        self.bridge.write(f"VOLT {vpp:.6E}", timeout=2.0)
        with self._lock:
            self._amplitude = float(vpp)

    def set_offset(self, volts: float) -> None:
        self.bridge.write(f"VOLT:OFFS {volts:.6E}", timeout=2.0)
        with self._lock:
            self._offset = float(volts)

    def set_phase(self, degrees: float) -> None:
        self.bridge.write(f"PHAS {degrees:.6E}", timeout=2.0)
        with self._lock:
            self._phase = float(degrees)

    def set_waveform(self, shape: str) -> None:
        shape = shape.strip().upper()
        if shape not in _VALID_WAVEFORMS:
            raise KeyError(
                f"Unknown waveform {shape!r}; "
                f"valid: {_VALID_WAVEFORMS}",
            )
        self.bridge.write(f"FUNC:SHAP {shape}", timeout=2.0)
        with self._lock:
            self._waveform = shape

    def set_duty_cycle(self, percent: float) -> None:
        """Set square-wave duty cycle (%). Valid only when waveform = SQU."""
        with self._lock:
            current_waveform = self._waveform
        if current_waveform != "SQU":
            raise ValueError(
                f"Duty cycle applies only to square wave (current: "
                f"{current_waveform}); set waveform to 'SQU' first.",
            )
        if not (20.0 <= percent <= 80.0):
            raise ValueError(
                f"33120A duty cycle must be 20%-80%, got {percent}",
            )
        self.bridge.write(f"PULS:DCYC {percent:.3f}", timeout=2.0)
        with self._lock:
            self._duty_cycle = float(percent)

    def set_output_enabled(self, enabled: bool) -> None:
        scpi = "ON" if enabled else "OFF"
        self.bridge.write(f"OUTP {scpi}", timeout=2.0)
        with self._lock:
            self._output_enabled = bool(enabled)

    def set_output_load(self, load: str) -> None:
        load = load.strip().upper()
        if load not in _VALID_LOADS:
            raise KeyError(
                f"Output load must be one of {_VALID_LOADS}, got {load!r}",
            )
        self.bridge.write(f"OUTP:LOAD {load}", timeout=2.0)
        with self._lock:
            self._output_load = load

    # -- Acquisition (SETPOINT model) --------------------------------

    def acquire(self, should_continue: Optional[callable] = None
                 ) -> Optional[GeneratorState]:
        """Read back current state from the instrument.

        A ``SETPOINT`` instrument's ``acquire`` is a status poll — it
        returns the current setpoints so the UI catches external
        changes (front panel, another program) and so the instrument's
        power-on state shows up correctly in the UI on connect.
        """
        if not self.bridge or not self.bridge.is_open:
            raise SerialBridgeError("Not connected")

        self._refresh_from_instrument()

        with self._lock:
            return GeneratorState(
                channel=1,
                output_enabled=self._output_enabled,
                timestamp=time.monotonic(),
                setpoints={
                    "frequency":   self._frequency,
                    "amplitude":   self._amplitude,
                    "offset":      self._offset,
                    "phase":       self._phase,
                    "waveform":    self._waveform,
                    "duty_cycle":  self._duty_cycle,
                    "output_load": self._output_load,
                },
                readback={},
                metadata={"model": "33120A"},
            )

    # -- Generic setting dispatcher ----------------------------------

    _SETTING_DISPATCH: dict[str, str] = {
        "frequency":       "set_frequency",
        "amplitude":       "set_amplitude",
        "offset":          "set_offset",
        "phase":           "set_phase",
        "waveform":        "set_waveform",
        "duty_cycle":      "set_duty_cycle",
        "output_enabled":  "set_output_enabled",
        "output_load":     "set_output_load",
    }

    def apply_setting(self, key: str, value: Any) -> None:
        method_name = self._SETTING_DISPATCH.get(key)
        if method_name is None:
            raise KeyError(
                f"Agilent33120ADriver: unknown setting {key!r}; "
                f"valid: {self.supported_settings()}",
            )
        getattr(self, method_name)(value)

    def read_setting(self, key: str) -> Any:
        with self._lock:
            return {
                "frequency":       self._frequency,
                "amplitude":       self._amplitude,
                "offset":          self._offset,
                "phase":           self._phase,
                "waveform":        self._waveform,
                "duty_cycle":      self._duty_cycle,
                "output_enabled":  self._output_enabled,
                "output_load":     self._output_load,
            }.get(key)

    def supported_settings(self) -> tuple[str, ...]:
        return tuple(self._SETTING_DISPATCH.keys())

    # -- Helpers ------------------------------------------------------

    @staticmethod
    def _check_range(name: str, value: float, *, lo: float, hi: float) -> None:
        if not (lo <= value <= hi):
            raise ValueError(
                f"{name} out of range: {value} (valid: {lo}..{hi})",
            )
