"""
Synthetic DMM bridge — lets the DMM driver run end-to-end without
real hardware.

Responds to standard SCPI DMM commands (``MEAS:VOLT:DC?``,
``MEAS:CURR:DC?``, etc.) with plausible values plus a small drift so
the min/max/avg tracking on the driver side has something to work
with. Duck-types the same ``Bridge`` protocol as ``SerialBridge`` and
``DemoBridge``, so LabSession can hand this to any DMM driver.
"""

from __future__ import annotations

import math
import random
import time


class DemoDMMBridge:
    """Bridge that answers SCPI DMM queries with synthetic readings.

    The driver polls ``MEAS:<fn>:<mode>?`` each tick; this bridge
    returns a slowly-drifting value centred on a nominal set per
    measurement function. Sufficient to exercise DMMDriver, MeterReading
    emission, and the DMMLayout UI without a real DMM attached.
    """

    # Nominal values (driven value before drift/noise added).
    NOMINALS = {
        "VOLT:DC": 3.3,
        "VOLT:AC": 0.120,
        "CURR:DC": 0.015,
        "CURR:AC": 0.001,
        "RES":     1000.0,      # 1 kΩ
        "FREQ":    1000.0,
        "CAP":     10e-9,
        "TEMP":    23.5,
    }

    NOISE_FRAC = 0.002   # ±0.2 %

    def __init__(self, model: str = "DEMO-DMM"):
        self._open = False
        self._model = model
        self._start = time.monotonic()

    # -- Bridge protocol ---------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def bridge_status(self) -> str:
        return "READY"

    @property
    def port(self) -> str:
        return "Demo DMM"

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def wait_for_status(self, target: str = "READY",
                         timeout: float = 30.0) -> str:
        return "READY"

    # -- SCPI -------------------------------------------------------

    def write(self, command: str, timeout: float | None = None) -> str:
        # DMM settings are stateless on this bridge — we just accept.
        return "OK"

    def query(self, command: str, timeout: float | None = None) -> str:
        cmd = command.strip().upper().rstrip("?")

        # *IDN? — discovery probe hits this during auto-detect.
        if cmd == "*IDN":
            return f"DemoInstruments,{self._model},DEMO-001,1.0"
        if cmd == "*OPC":
            return "1"

        # MEAS:VOLT:DC, MEAS:CURR:AC, MEAS:RES, MEAS:FREQ, MEAS:TEMP, …
        if cmd.startswith("MEAS:") or cmd.startswith("MEASURE:"):
            payload = cmd.split(":", 1)[1] if ":" in cmd else ""
            payload = payload.removeprefix("URE:") if payload.startswith("URE:") else payload
            value = self._synthesize(payload)
            return f"{value:.6E}"

        # READ? — common "repeat last measurement" alias.
        if cmd == "READ":
            return f"{self._synthesize('VOLT:DC'):.6E}"

        return "0"

    def query_binary(self, command: str,
                      timeout: float | None = None) -> bytes:
        # DMMs don't emit block data — the method exists only to
        # satisfy the Bridge protocol.
        return b""

    # -- Synthesis ---------------------------------------------------

    def _synthesize(self, function: str) -> float:
        """Return a drifting value for the requested SCPI measurement."""
        nominal = self.NOMINALS.get(function.strip(), 0.0)
        elapsed = time.monotonic() - self._start
        # Slow sinusoidal drift + white noise so min/max/avg on the
        # driver side track something non-trivial.
        drift = 0.005 * math.sin(elapsed * 0.4)
        noise = random.uniform(-self.NOISE_FRAC, self.NOISE_FRAC)
        return nominal * (1.0 + drift + noise)
