"""
Synthetic function-generator bridge.

Duck-types the ``Bridge`` protocol the real ``SerialBridge`` implements.
Stores setpoints in memory and echoes them back on query, so the
driver's ``acquire()`` returns a coherent ``GeneratorState`` without
hardware. Also answers ``*IDN?`` with a plausible 33120A identity
so the discovery + registry path matches.
"""

from __future__ import annotations


class DemoFuncGenBridge:
    """Mock bridge for function-generator testing + demo mode.

    Responds to the SCPI commands the driver sends (FREQ, VOLT, VOLT:OFFS,
    FUNC:SHAP, OUTP, OUTP:LOAD, PHAS). Unknown commands return "0" so
    the bridge never stalls a test; unknown writes silently accept.
    """

    def __init__(self, model: str = "33120A"):
        self._open = False
        self._model = model

        # Default state — matches a 33120A just after *RST.
        self._state: dict[str, str] = {
            "FREQ":       "1.000000E+03",   # 1 kHz
            "VOLT":       "1.000000E-01",   # 100 mVpp default after reset
            "VOLT:OFFS":  "0.000000E+00",
            "FUNC:SHAP":  "SIN",
            "OUTP":       "0",               # Output OFF after *RST
            "OUTP:LOAD":  "50",
            "PHAS":       "0.000000E+00",
        }

    # -- Bridge protocol ---------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def bridge_status(self) -> str:
        return "READY"

    @property
    def port(self) -> str:
        return "Demo Function Generator"

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def wait_for_status(self, target: str = "READY",
                         timeout: float = 30.0) -> str:
        return "READY"

    # -- SCPI --------------------------------------------------------

    def write(self, command: str, timeout: float | None = None) -> str:
        """Accept setpoint writes and remember them."""
        cmd = command.strip()

        # *RST: reset everything to factory defaults. Useful for tests.
        if cmd.upper() == "*RST":
            self.__init__(model=self._model)
            self._open = True
            return "OK"

        # Parse "NOUN[:SUFFIX] VALUE" — the 33120A's write commands
        # follow this shape. Everything left of the space is the key;
        # everything right is the value.
        if " " in cmd:
            key, value = cmd.split(" ", 1)
            key = key.strip().upper()
            value = value.strip()

            # Normalise boolean "ON"/"OFF" to "1"/"0" for OUTP.
            if key == "OUTP":
                up = value.upper()
                if up in ("ON", "1"):
                    value = "1"
                elif up in ("OFF", "0"):
                    value = "0"

            # Normalise waveform shape to upper case.
            if key == "FUNC:SHAP":
                value = value.upper()

            self._state[key] = value
        return "OK"

    def query(self, command: str, timeout: float | None = None) -> str:
        cmd = command.strip().upper().rstrip("?")

        if cmd == "*IDN":
            return f"HEWLETT-PACKARD,{self._model},0,REV A.02.00"
        if cmd == "*OPC":
            return "1"

        if cmd in self._state:
            return self._state[cmd]

        # Unknown query — return "0" so callers don't hang.
        return "0"

    def query_binary(self, command: str,
                      timeout: float | None = None) -> bytes:
        # Func-gens don't produce binary data on the SCPI path.
        return b""
