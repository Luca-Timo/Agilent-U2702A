"""
Generic SCPI DMM driver.

Targets the standard IEEE-488.2 / SCPI-99 measurement commands
(``MEAS:VOLT:DC?``, ``MEAS:CURR:AC?``, ``MEAS:RES?``, …) that most
bench DMMs from Keithley, Keysight, Rigol, Siglent, etc. implement.
Add a model-specific preset (``config/presets/your_model.py``) plus
an entry in ``automation.session.DRIVER_REGISTRY`` to expose a new
DMM to ``LabSession``.

Per the lab-bench rules the driver:
  - never imports from ``gui/``
  - is synchronous and thread-safe via ``threading.Lock``
  - returns a ``MeterReading`` from ``acquire()``

This lands in ``instrument/drivers/`` not to supplant future
model-specific drivers but to give them a batteries-included starting
point — subclasses that need non-standard commands override
``_measure_cmd`` or specific apply-setting handlers.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from typing import Any, Optional

from config import DMMConfig
from instrument.capabilities import Capabilities, DMM_DEFAULTS
from instrument.driver import Bridge
from instrument.serial_bridge import SerialBridgeError
from processing.acquisition_result import MeterReading

logger = logging.getLogger(__name__)


# SCPI measurement function codes. The driver's ``mode`` setting stores
# one of these; ``_measure_cmd`` formats it into a ``MEAS:<code>?`` query.
# Users don't see the raw codes — the GUI's DMM mode selector speaks
# friendly names ("DCV", "ACV", "DCI", "ACI", "Ω", "Freq", "Cap", "°C").
_MODE_TO_SCPI = {
    "DCV":  ("VOLT:DC", "V"),
    "ACV":  ("VOLT:AC", "V"),
    "DCI":  ("CURR:DC", "A"),
    "ACI":  ("CURR:AC", "A"),
    "RES":  ("RES",     "Ω"),
    "FREQ": ("FREQ",    "Hz"),
    "CAP":  ("CAP",     "F"),
    "TEMP": ("TEMP",    "°C"),
}


class GenericDMMDriver:
    """SCPI-standard DMM driver. Implements ``InstrumentDriver``.

    Emits one ``MeterReading`` per ``acquire()`` call, tracking
    min/max/avg across readings so the UI can display running
    statistics without re-computing them on every paint.
    """

    def __init__(self, bridge: Bridge, config: Optional[DMMConfig] = None):
        self.bridge = bridge
        self._config = config

        caps = DMM_DEFAULTS
        if config is not None:
            caps = replace(caps, num_channels=config.num_channels)
        self.capabilities: Capabilities = caps

        self._lock = threading.Lock()
        self._mode: str = "DCV"            # active measurement function
        self._range: str = "AUTO"
        self._channel: int = 1
        self._hold: bool = False           # freeze the last reading
        self._last_reading: Optional[MeterReading] = None

        # Running accumulator (min / max / avg) — kept per-mode so
        # switching modes doesn't corrupt the stats.
        self._acc: dict[str, dict] = {}

    # -- Lifecycle ---------------------------------------------------

    def open(self) -> None:
        if not self.bridge.is_open:
            self.bridge.open()

    def close(self) -> None:
        if self.bridge and self.bridge.is_open:
            self.bridge.close()

    def init_sequence(self) -> dict:
        """Probe IDN and return a basic state dict.

        Most DMMs don't need a multi-step init — the first measurement
        query implicitly selects the function. Subclasses override this
        for DMMs with required setup sequences.
        """
        idn = ""
        try:
            idn = self.bridge.query("*IDN?", timeout=1.5).strip()
        except SerialBridgeError as e:
            logger.warning("*IDN? failed during init: %s", e)
        with self._lock:
            return {
                "idn": idn,
                "mode": self._mode,
                "range": self._range,
                "channel": self._channel,
                "hold": self._hold,
            }

    # -- Typed setters ------------------------------------------------

    def set_mode(self, mode: str) -> None:
        if mode not in _MODE_TO_SCPI:
            raise KeyError(
                f"Unknown DMM mode {mode!r}; "
                f"valid modes: {tuple(_MODE_TO_SCPI)}",
            )
        with self._lock:
            self._mode = mode
            # Reset accumulator for the new function.
            self._acc.pop(mode, None)

    def set_range(self, range_spec: str) -> None:
        with self._lock:
            self._range = range_spec

    def set_hold(self, hold: bool) -> None:
        with self._lock:
            self._hold = bool(hold)

    def set_channel(self, channel: int) -> None:
        with self._lock:
            self._channel = int(channel)

    # -- Acquisition --------------------------------------------------

    def acquire(self, should_continue: Optional[callable] = None) -> Optional[MeterReading]:
        """Take one reading. Returns a ``MeterReading`` or ``None`` if
        the driver is on hold (UI displays the last value)."""
        if not self.bridge or not self.bridge.is_open:
            raise SerialBridgeError("Not connected")

        with self._lock:
            mode = self._mode
            hold = self._hold
            channel = self._channel
            range_spec = self._range

        if hold and self._last_reading is not None:
            # Return the cached reading with a fresh timestamp so
            # subscribers still see a heartbeat. None signals "no new
            # reading" — callers decide whether to re-emit the cached
            # value. The GUI's DMM mode keeps the display frozen.
            return None

        scpi_code, unit = _MODE_TO_SCPI[mode]
        cmd = f"MEAS:{scpi_code}?"

        # Some DMMs need the range baked into the MEAS query (e.g.
        # "MEAS:VOLT:DC? 10"); skipped for AUTO. Subclasses override
        # for non-standard range syntax.
        if range_spec and range_spec != "AUTO":
            cmd = f"MEAS:{scpi_code}? {range_spec}"

        reply = self.bridge.query(cmd, timeout=2.0)
        try:
            value = float(reply.strip())
        except ValueError as e:
            raise SerialBridgeError(
                f"Non-numeric DMM reply to {cmd!r}: {reply!r}",
            ) from e

        reading = self._track(mode, channel, value, unit, range_spec)
        self._last_reading = reading
        return reading

    def _track(self, mode: str, channel: int, value: float,
                unit: str, range_spec: str) -> MeterReading:
        """Update running min/max/avg for the mode and return a ``MeterReading``."""
        now = time.monotonic()
        with self._lock:
            acc = self._acc.setdefault(mode, {
                "min": value, "max": value, "sum": 0.0, "n": 0,
            })
            acc["min"] = min(acc["min"], value)
            acc["max"] = max(acc["max"], value)
            acc["sum"] += value
            acc["n"] += 1
            avg = acc["sum"] / acc["n"]
            mn, mx, n = acc["min"], acc["max"], acc["n"]

        return MeterReading(
            channel=channel,
            primary=value,
            unit=unit,
            timestamp=now,
            minimum=mn,
            maximum=mx,
            average=avg,
            samples=n,
            range=range_spec,
            metadata={"mode": mode},
        )

    def reset_stats(self) -> None:
        """Clear the min/max/avg accumulator for every mode."""
        with self._lock:
            self._acc.clear()

    # -- Generic setting dispatcher ----------------------------------

    _SETTING_DISPATCH: dict[str, str] = {
        "mode":    "set_mode",
        "range":   "set_range",
        "hold":    "set_hold",
        "channel": "set_channel",
    }

    def apply_setting(self, key: str, value: Any) -> None:
        method_name = self._SETTING_DISPATCH.get(key)
        if method_name is None:
            raise KeyError(
                f"GenericDMMDriver: unknown setting {key!r}; "
                f"try one of {self.supported_settings()}",
            )
        getattr(self, method_name)(value)

    def read_setting(self, key: str) -> Any:
        with self._lock:
            return {
                "mode":    self._mode,
                "range":   self._range,
                "hold":    self._hold,
                "channel": self._channel,
            }.get(key)

    def supported_settings(self) -> tuple[str, ...]:
        return tuple(self._SETTING_DISPATCH.keys())
