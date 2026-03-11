"""
Demo signal bridge — generates synthetic waveforms for GUI testing.

Duck-types SerialBridge so the entire GUI works without real hardware.
Produces a 1 kHz 3.3 V 50% PWM signal.
"""

import time
import numpy as np


# --- Waveform format (must match processing/waveform.py) ---
ADC_DATA_LENGTH = 1256
ADC_CENTER = 128
ADC_RANGE = 256
NUM_V_DIVS = 8
NUM_H_DIVS = 10
PAYLOAD_SIZE = 2514  # 2 prefix + 1256 ADC + 1256 padding

# Demo signal parameters
PWM_FREQ_HZ = 1000.0       # 1 kHz
PWM_DUTY = 0.5              # 50%
PWM_HIGH_V = 3.3            # Volts
PWM_LOW_V = 0.0             # Volts
NOISE_COUNTS = 1            # ±1 ADC count noise


class DemoBridge:
    """Mock bridge that generates synthetic PWM waveforms.

    Implements the same public interface as SerialBridge so the
    acquisition worker and GUI are unaware of the difference.
    """

    def __init__(self):
        # Per-channel state (channels 1 and 2)
        self._channels = {
            1: {"v_per_div": 1.0, "offset": 0.0, "enabled": True,
                "coupling": "DC", "bw_limit": False, "probe": 1.0},
            2: {"v_per_div": 1.0, "offset": 0.0, "enabled": False,
                "coupling": "DC", "bw_limit": False, "probe": 1.0},
        }

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
        for ch in (1, 2):
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
        for ch in (1, 2):
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
            return f"{self._t_per_div * NUM_H_DIVS:.6E}"
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
        """Generate synthetic PWM waveform data."""
        # Simulate acquisition delay
        time.sleep(0.020)

        ch = self._wav_source
        s = self._channels.get(ch, self._channels[1])
        v_per_div = s["v_per_div"]

        # Volts per ADC count
        volts_per_count = (NUM_V_DIVS * v_per_div) / ADC_RANGE

        # Time per sample
        total_time = NUM_H_DIVS * self._t_per_div
        dt = total_time / ADC_DATA_LENGTH

        # Generate PWM: time array for each sample
        period = 1.0 / PWM_FREQ_HZ
        t = np.arange(ADC_DATA_LENGTH) * dt

        # Phase so signal is continuous across acquisitions
        phase = (time.monotonic() % period)
        t_in_cycle = (t + phase) % period

        # PWM: high when in first half of cycle
        voltage = np.where(
            t_in_cycle < period * PWM_DUTY,
            PWM_HIGH_V, PWM_LOW_V,
        )

        # Convert to ADC counts (inverse of adc_to_voltage, without offset)
        raw = (voltage / volts_per_count) + ADC_CENTER

        # Add noise
        raw += np.random.randint(-NOISE_COUNTS, NOISE_COUNTS + 1,
                                 size=ADC_DATA_LENGTH)

        # Clamp to uint8
        raw = np.clip(raw, 0, 255).astype(np.uint8)

        # Build payload: [2 prefix] [1256 ADC] [1256 padding]
        prefix = b'\x01\x00'
        padding = b'\x00' * (PAYLOAD_SIZE - 2 - ADC_DATA_LENGTH)
        return prefix + raw.tobytes() + padding
