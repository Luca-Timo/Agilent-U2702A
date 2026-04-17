"""
Demo signal bridge — generates synthetic waveforms for GUI testing.

Duck-types SerialBridge so the entire GUI works without real hardware.
Generates the test signal configured in ``SCOPE.demo_signal`` (default:
1 kHz 3.3 V 50% PWM).
"""

import time

import numpy as np

from config import SCOPE


class DemoBridge:
    """Mock bridge that generates synthetic waveforms.

    Implements the same public interface as SerialBridge so the
    acquisition worker and GUI are unaware of the difference.
    """

    def __init__(self):
        # Per-channel state: only CH1 enabled by default.
        self._channels = {}
        for ch in range(1, SCOPE.num_channels + 1):
            self._channels[ch] = {
                "v_per_div": 1.0,
                "offset": 0.0,
                "enabled": (ch == 1),
                "coupling": "DC",
                "bw_limit": False,
                "probe": 1.0,
            }

        # Pre-allocate scratch buffers for waveform generation (hot path).
        adc_len = SCOPE.adc.data_length
        self._t_buf = np.empty(adc_len, dtype=np.float64)
        self._raw_buf = np.empty(adc_len, dtype=np.float64)
        self._idx = np.arange(adc_len, dtype=np.float64)
        self._padding = b'\x00' * (
            SCOPE.adc.payload_size - SCOPE.adc.data_offset - adc_len
        )
        self._prefix = b'\x01\x00'

        # Timebase
        self._t_per_div = 1e-3
        self._position = 0.0

        # Trigger
        self._trigger_level = 1.5
        self._trigger_source = "CHAN1"
        self._trigger_slope = "POS"
        self._trigger_sweep = "AUTO"
        self._trigger_coupling = "DC"

        # WAV:SOUR channel
        self._wav_source = 1

        self._open = False

    # --- Properties (SerialBridge interface) ---

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def bridge_status(self) -> str:
        return "READY"

    @property
    def port(self) -> str:
        return "Demo Signal"

    # --- Connection (no-ops) ---

    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def wait_for_status(self, target: str = "READY",
                        timeout: float = 30.0) -> str:
        return "READY"

    # --- Command interface ---

    def write(self, command: str, timeout: float = None) -> str:
        """Accept set commands and update internal state."""
        cmd = command.strip().upper()

        # Channel settings: CHANNEL1:SCALE 0.5
        for ch in range(1, SCOPE.num_channels + 1):
            prefix = f"CHANNEL{ch}:"
            if cmd.startswith(prefix):
                rest = cmd[len(prefix):]
                if rest.startswith("SCALE "):
                    self._channels[ch]["v_per_div"] = float(rest[6:])
                elif rest.startswith("OFFSET "):
                    self._channels[ch]["offset"] = float(rest[7:])
                elif rest.startswith("DISPLAY "):
                    self._channels[ch]["enabled"] = rest[8:] in ("1", "ON")
                elif rest.startswith("COUPLING "):
                    self._channels[ch]["coupling"] = rest[9:]
                elif rest.startswith("BWLIMIT "):
                    self._channels[ch]["bw_limit"] = rest[8:] in ("1", "ON")
                return "OK"

        # Timebase
        if cmd.startswith("TIM:SCAL ") or cmd.startswith("TIMEBASE:SCALE "):
            self._t_per_div = float(cmd.split()[-1])
        elif cmd.startswith("TIMEBASE:POS ") or cmd.startswith("TIM:POS "):
            self._position = float(cmd.split()[-1])

        # Trigger
        elif cmd.startswith("TRIGGER:EDGE:LEVEL ") or \
                cmd.startswith("TRIG:EDGE:LEVEL "):
            self._trigger_level = float(cmd.split()[-1])
        elif cmd.startswith("TRIGGER:EDGE:SOURCE ") or \
                cmd.startswith("TRIG:EDGE:SOUR "):
            self._trigger_source = cmd.split()[-1]
        elif cmd.startswith("TRIG:EDGE:SLOPE ") or \
                cmd.startswith("TRIGGER:EDGE:SLOPE "):
            self._trigger_slope = cmd.split()[-1]
        elif cmd.startswith("TRIGGER:SWEEP ") or \
                cmd.startswith("TRIG:SWEEP "):
            self._trigger_sweep = cmd.split()[-1]
        elif cmd.startswith("TRIGGER:EDGE:COUPLING "):
            self._trigger_coupling = cmd.split()[-1]

        # WAV source
        elif cmd.startswith("WAV:SOUR "):
            src = cmd.split()[-1]
            if src.startswith("CHAN"):
                self._wav_source = int(src[4:])

        return "OK"

    def query(self, command: str, timeout: float = None) -> str:
        """Return state values for query commands."""
        cmd = command.strip().upper().rstrip("?")

        # Channel queries
        for ch in range(1, SCOPE.num_channels + 1):
            prefix = f"CHANNEL{ch}:"
            if cmd.startswith(prefix):
                key = cmd[len(prefix):]
                s = self._channels[ch]
                if key == "SCALE":
                    return f"{s['v_per_div']:.6E}"
                elif key == "OFFSET":
                    return f"{s['offset']:.6E}"
                elif key == "DISPLAY":
                    return "1" if s["enabled"] else "0"
                elif key == "COUPLING":
                    return s["coupling"]
                elif key == "BWLIMIT":
                    return "1" if s["bw_limit"] else "0"

        # Timebase queries
        if cmd in ("TIM:SCAL", "TIMEBASE:SCALE"):
            return f"{self._t_per_div:.6E}"
        if cmd in ("TIMEBASE:POS", "TIM:POS"):
            return f"{self._position:.6E}"
        if cmd == "TIM:RANG":
            return f"{self._t_per_div * SCOPE.grid.horizontal_divs:.6E}"
        if cmd == "TIM:REF":
            return "CENT"
        if cmd == "TIM:MODE":
            return "MAIN"

        # Trigger queries
        if cmd in ("TRIGGER:EDGE:LEVEL", "TRIG:EDGE:LEVEL"):
            return f"{self._trigger_level:.6E}"
        if cmd in ("TRIGGER:EDGE:SOURCE", "TRIG:EDGE:SOUR"):
            return self._trigger_source
        if cmd in ("TRIG:EDGE:SLOPE", "TRIGGER:EDGE:SLOPE"):
            return self._trigger_slope
        if cmd in ("TRIGGER:SWEEP", "TRIG:SWEEP"):
            return self._trigger_sweep
        if cmd in ("TRIGGER:EDGE:COUPLING",):
            return self._trigger_coupling
        if cmd == "TRIGGER:MODE":
            return "EDGE"

        # Acquisition / misc
        if cmd == "ACQ:TYPE":
            return "NORM"
        if cmd == "*OPC":
            return "1"

        # Default: return "0" for unknown queries
        return "0"

    def query_binary(self, command: str, timeout: float = None) -> bytes:
        """Generate a synthetic waveform payload for demo mode."""
        # Simulate acquisition delay
        time.sleep(0.020)

        adc = SCOPE.adc
        grid = SCOPE.grid
        sig = SCOPE.demo_signal

        ch = self._wav_source
        s = self._channels.get(ch, self._channels[1])
        v_per_div = s["v_per_div"]

        # Volts per ADC count
        volts_per_count = (grid.vertical_divs * v_per_div) / adc.range

        # Time per sample
        dt = (grid.horizontal_divs * self._t_per_div) / adc.data_length

        # Time array (reuse preallocated index buffer, write into t_buf)
        np.multiply(self._idx, dt, out=self._t_buf)

        # Signal phase continuity across acquisitions
        period = 1.0 / sig.frequency_hz
        phase = time.monotonic() % period
        t_in_cycle = np.mod(self._t_buf + phase, period)

        # PWM: high when in first (duty) fraction of the cycle.
        # Fill _raw_buf via boolean indexing (no allocation beyond the mask).
        hi = sig.high_v / volts_per_count + adc.center
        lo = sig.low_v / volts_per_count + adc.center
        mask = t_in_cycle < period * sig.duty
        self._raw_buf[mask] = hi
        self._raw_buf[~mask] = lo

        # Add integer noise
        if sig.noise_counts > 0:
            self._raw_buf += np.random.randint(
                -sig.noise_counts, sig.noise_counts + 1, size=adc.data_length,
            )

        # Clamp to uint8 in one pass
        raw = np.clip(self._raw_buf, 0, adc.range - 1).astype(np.uint8)

        # Build payload: [prefix] [ADC data] [padding]
        return self._prefix + raw.tobytes() + self._padding
