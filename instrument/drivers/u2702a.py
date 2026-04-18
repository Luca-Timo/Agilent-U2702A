"""
Agilent U2702A oscilloscope driver.

Implements the ``InstrumentDriver`` protocol with no Qt dependency —
the same methods are called by the Qt acquisition worker (GUI path)
and by automation scripts (headless path). State is guarded by a
``threading.Lock`` so either caller can drive the instrument safely.

Scope-specific SCPI dialect lives in ``instrument.protocol``; this
module composes those builders into a coherent driver with settings
management and an acquisition loop.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Optional

from config import SCOPE
from instrument import protocol
from instrument.capabilities import Capabilities, OSCILLOSCOPE_DEFAULTS
from instrument.driver import Bridge
from instrument.serial_bridge import (
    BridgeProtocolError,
    BridgeTimeoutError,
    SerialBridgeError,
)
from processing.waveform import (
    WaveformData,
    adc_to_voltage,
    find_trigger_crossing,
    make_time_axis,
    parse_wav_data,
)

logger = logging.getLogger(__name__)


@dataclass
class ChannelSettings:
    """Instrument-side settings for one channel."""

    enabled: bool = False
    v_per_div: float = 1.0
    offset: float = 0.0
    coupling: str = "DC"
    bw_limit: bool = False
    probe_factor: float = 1.0


class U2702ADriver:
    """Concrete InstrumentDriver for the Agilent U2702A.

    Synchronous: every method returns when the SCPI round-trip is
    complete. The GUI wraps this in a QThread for the acquisition loop;
    scripts call the methods directly.
    """

    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.capabilities: Capabilities = replace(
            OSCILLOSCOPE_DEFAULTS, num_channels=SCOPE.num_channels,
        )

        # Lock guards all mutable state below. Every method either
        # takes the lock briefly to mutate / snapshot, then releases
        # before doing SCPI I/O — bridge writes are already thread-safe
        # on their own (SerialBridge has its own internal lock).
        self._lock = threading.Lock()

        self._channels: dict[int, ChannelSettings] = {}
        self._enabled_channels: list[int] = [1]
        self._t_per_div: float = 1e-3
        self._trigger_level: float = 0.0
        self._trigger_slope: str = "POS"
        self._trigger_source: str = "CHAN1"

    # -- Lifecycle ----------------------------------------------------

    def open(self) -> None:
        if not self.bridge.is_open:
            self.bridge.open()

    def close(self) -> None:
        if self.bridge and self.bridge.is_open:
            self.bridge.close()

    def init_sequence(self) -> dict:
        """Run the post-connect query sequence and return parsed state."""
        state: dict[str, str] = {}
        init_seq = protocol.build_init_sequence(self.capabilities.num_channels)
        for cmd in init_seq:
            if cmd.endswith("?"):
                resp = self.bridge.query(cmd, timeout=2.0)
                state[cmd] = resp.strip()
            else:
                self.bridge.write(cmd, timeout=2.0)
                state[cmd] = "OK"
            # Small sleep to match the original init cadence; the U2702A
            # is picky about back-to-back queries.
            time.sleep(0.02)
        return self._parse_init_state(state)

    def _parse_init_state(self, raw: dict) -> dict:
        parsed: dict[str, Any] = {"channels": {}, "timebase": {}, "trigger": {}}

        for ch in range(1, self.capabilities.num_channels + 1):
            ch_state: dict[str, Any] = {}
            for key, field, coerce in (
                (f"CHANNEL{ch}:SCALE?", "v_per_div", float),
                (f"CHANNEL{ch}:OFFSET?", "offset", float),
                (f"CHANNEL{ch}:DISPLAY?", "enabled",
                    lambda s: s.strip() in ("1", "ON")),
                (f"CHANNEL{ch}:COUPLING?", "coupling",
                    lambda s: s.strip()),
                (f"CHANNEL{ch}:BWLIMIT?", "bw_limit",
                    lambda s: s.strip() in ("1", "ON")),
            ):
                if key in raw:
                    try:
                        ch_state[field] = coerce(raw[key])
                    except (ValueError, TypeError):
                        pass
            parsed["channels"][ch] = ch_state

        if "TIM:SCAL?" in raw:
            try:
                parsed["timebase"]["t_per_div"] = float(raw["TIM:SCAL?"])
            except ValueError:
                pass
        if "TIMEBASE:POS?" in raw:
            try:
                parsed["timebase"]["position"] = float(raw["TIMEBASE:POS?"])
            except ValueError:
                pass

        trg = parsed["trigger"]
        if "TRIGGER:EDGE:SOURCE?" in raw:
            trg["source"] = raw["TRIGGER:EDGE:SOURCE?"].strip()
        if "TRIGGER:EDGE:LEVEL?" in raw:
            try:
                trg["level"] = float(raw["TRIGGER:EDGE:LEVEL?"])
            except ValueError:
                pass
        if "TRIG:EDGE:SLOPE?" in raw:
            trg["slope"] = raw["TRIG:EDGE:SLOPE?"].strip()
        if "TRIGGER:SWEEP?" in raw:
            trg["sweep"] = raw["TRIGGER:SWEEP?"].strip()
        if "TRIGGER:EDGE:COUPLING?" in raw:
            trg["coupling"] = raw["TRIGGER:EDGE:COUPLING?"].strip()

        # Cache trigger info locally for software trigger alignment.
        with self._lock:
            if "level" in trg:
                self._trigger_level = trg["level"]
            if "slope" in trg:
                self._trigger_slope = trg["slope"]
            if "source" in trg:
                self._trigger_source = trg["source"]

        return parsed

    # -- Channel settings --------------------------------------------

    def _ensure_channel(self, ch: int) -> ChannelSettings:
        """Create a default ChannelSettings if one isn't yet tracked.

        Caller must hold ``self._lock``.
        """
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        return self._channels[ch]

    def set_channel_enabled(self, ch: int, enabled: bool) -> None:
        with self._lock:
            self._ensure_channel(ch).enabled = enabled
            self._enabled_channels = [
                c for c, s in self._channels.items() if s.enabled
            ]

    def set_vdiv(self, ch: int, value: float) -> None:
        with self._lock:
            self._ensure_channel(ch).v_per_div = value
        self.bridge.write(protocol.channel_scale_set(ch, value), timeout=2.0)

    def set_offset(self, ch: int, value: float) -> None:
        with self._lock:
            self._ensure_channel(ch).offset = value
        self.bridge.write(protocol.channel_offset_set(ch, value), timeout=2.0)

    def set_coupling(self, ch: int, coupling: str) -> None:
        with self._lock:
            self._ensure_channel(ch).coupling = coupling
        self.bridge.write(protocol.channel_coupling_set(ch, coupling), timeout=2.0)

    def set_bwlimit(self, ch: int, enabled: bool) -> None:
        with self._lock:
            self._ensure_channel(ch).bw_limit = enabled
        self.bridge.write(protocol.channel_bwlimit_set(ch, enabled), timeout=2.0)

    def set_probe(self, ch: int, factor: float) -> None:
        # Probe factor is GUI-display-only on the U2702A (no SCPI).
        with self._lock:
            self._ensure_channel(ch).probe_factor = factor

    # -- Timebase -----------------------------------------------------

    def set_tdiv(self, value: float) -> None:
        with self._lock:
            self._t_per_div = value
        self.bridge.write(protocol.timebase_scale_set(value), timeout=2.0)
        self.bridge.write(protocol.timebase_position_set(0), timeout=2.0)

    def set_position(self, value: float) -> None:
        self.bridge.write(protocol.timebase_position_set(value), timeout=2.0)

    # -- Trigger ------------------------------------------------------

    def set_trigger_level(self, value: float) -> None:
        with self._lock:
            self._trigger_level = value
        self.bridge.write(protocol.trigger_edge_level_set(value), timeout=2.0)

    def set_trigger_source(self, source: str) -> None:
        with self._lock:
            self._trigger_source = source
        self.bridge.write(protocol.trigger_edge_source_set(source), timeout=2.0)

    def set_trigger_slope(self, slope: str) -> None:
        with self._lock:
            self._trigger_slope = slope
        self.bridge.write(protocol.trigger_edge_slope_set(slope), timeout=2.0)

    def set_trigger_sweep(self, mode: str) -> None:
        self.bridge.write(protocol.trigger_sweep_set(mode), timeout=2.0)

    def set_trigger_coupling(self, coupling: str) -> None:
        self.bridge.write(protocol.trigger_edge_coupling_set(coupling), timeout=2.0)

    # -- Trigger mode + Pulse-width (glitch) trigger -----------------

    def set_trigger_mode(self, mode: str) -> None:
        """Switch between trigger subsystems.

        Valid: ``EDGE`` (the default), ``GLITCH`` (pulse width),
        ``TV``, ``PATTERN``. The U2702A handles each subsystem's
        parameters independently — switching mode doesn't lose the
        per-subsystem settings.
        """
        self.bridge.write(protocol.trigger_mode_set(mode), timeout=2.0)

    def set_trigger_pulse_polarity(self, polarity: str) -> None:
        """``POS`` = positive-going pulse, ``NEG`` = negative."""
        self.bridge.write(
            protocol.trigger_glitch_polarity_set(polarity), timeout=2.0,
        )

    def set_trigger_pulse_qualifier(self, qualifier: str) -> None:
        """Pulse-width comparison: ``LESS``, ``GRE``, ``RANG``, ``OUTRANG``."""
        self.bridge.write(
            protocol.trigger_glitch_qualifier_set(qualifier), timeout=2.0,
        )

    def set_trigger_pulse_greater(self, seconds: float) -> None:
        """Threshold for the GRE (greater-than) qualifier."""
        self.bridge.write(
            protocol.trigger_glitch_greater_set(seconds), timeout=2.0,
        )

    def set_trigger_pulse_less(self, seconds: float) -> None:
        """Threshold for the LESS qualifier."""
        self.bridge.write(
            protocol.trigger_glitch_less_set(seconds), timeout=2.0,
        )

    def set_trigger_pulse_range(self, min_s: float, max_s: float) -> None:
        """Window for the RANG / OUTRANG qualifiers."""
        self.bridge.write(
            protocol.trigger_glitch_range_set(min_s, max_s), timeout=2.0,
        )

    def set_trigger_pulse_source(self, source: str) -> None:
        """Channel the pulse-width comparator watches, e.g. ``CHAN1``."""
        self.bridge.write(
            protocol.trigger_glitch_source_set(source), timeout=2.0,
        )

    # -- Acquisition --------------------------------------------------

    @dataclass
    class AcquireResult:
        """One acquisition step: per-channel waveforms + trigger state."""

        waveforms: list[WaveformData]
        trigger_found: bool
        trigger_source_ch: Optional[int]   # present regardless of visibility

    def _snapshot(self):
        """Grab a coherent snapshot of settings for one acquisition pass."""
        with self._lock:
            return (
                list(self._enabled_channels),
                self._t_per_div,
                self._trigger_level,
                self._trigger_slope,
                self._trigger_source,
                {ch: replace(s) for ch, s in self._channels.items()},
            )

    def acquire(
        self,
        should_continue: Optional[callable] = None,
    ) -> "U2702ADriver.AcquireResult":
        """Fire one ``:SINGLE`` and read data for every enabled channel.

        Args:
            should_continue: Optional callable; when provided the driver
                checks it between per-channel reads and bails out early
                if it returns False. Scripts normally pass ``None``; the
                GUI worker passes ``lambda: self._is_running()`` so
                ``stop()`` aborts cleanly mid-frame.

        Returns an ``AcquireResult``. Raises ``SerialBridgeError`` on
        transport failure; callers decide whether to keep looping.
        """
        if not self.bridge or not self.bridge.is_open:
            raise SerialBridgeError("Not connected")

        (enabled_channels, t_per_div, trigger_level, trigger_slope,
         trigger_source, channels_snapshot) = self._snapshot()

        # Enable every needed channel before arming. If any fails we
        # abort — partial enable produces inconsistent captures.
        for ch in enabled_channels:
            self.bridge.write(
                protocol.channel_display_set(ch, True), timeout=1.0,
            )

        self.bridge.write(protocol.SINGLE, timeout=1.0)

        trig_ch = None
        if trigger_source.startswith("CHAN"):
            try:
                trig_ch = int(trigger_source[4:])
            except ValueError:
                trig_ch = None

        ordered = list(enabled_channels)
        trig_ch_hidden = False
        if trig_ch is not None and trig_ch not in ordered:
            ordered.insert(0, trig_ch)
            trig_ch_hidden = True
        elif trig_ch in ordered:
            ordered.remove(trig_ch)
            ordered.insert(0, trig_ch)

        trigger_sample: Optional[int] = None
        trigger_found = False
        emitted: list[WaveformData] = []

        for i, ch in enumerate(ordered):
            if should_continue is not None and not should_continue():
                break
            waveform = self._read_channel_data(
                ch,
                poll=(i == 0),
                trigger_sample=trigger_sample,
                settings=channels_snapshot.get(ch, ChannelSettings()),
                t_per_div=t_per_div,
                should_continue=should_continue,
            )
            if not waveform:
                continue

            if ch == trig_ch and trigger_sample is None:
                adjusted_level = trigger_level + waveform.offset
                trigger_sample = find_trigger_crossing(
                    waveform.voltage, adjusted_level, trigger_slope,
                )
                if trigger_sample is not None:
                    trigger_found = True
                    waveform.trigger_sample = trigger_sample
                    waveform.time_axis = make_time_axis(
                        len(waveform.raw_adc), t_per_div,
                        trigger_sample=trigger_sample,
                    )

            if not (ch == trig_ch and trig_ch_hidden):
                emitted.append(waveform)

        return self.AcquireResult(
            waveforms=emitted,
            trigger_found=trigger_found,
            trigger_source_ch=trig_ch,
        )

    def _read_channel_data(
        self,
        ch: int,
        *,
        poll: bool = True,
        trigger_sample: Optional[int] = None,
        settings: Optional[ChannelSettings] = None,
        t_per_div: Optional[float] = None,
        should_continue: Optional[callable] = None,
    ) -> Optional[WaveformData]:
        if settings is None:
            with self._lock:
                settings = replace(self._channels.get(ch, ChannelSettings()))
                if t_per_div is None:
                    t_per_div = self._t_per_div
        elif t_per_div is None:
            with self._lock:
                t_per_div = self._t_per_div

        self.bridge.write(protocol.wav_source_set(ch), timeout=1.0)

        max_polls = 50 if poll else 10
        for _ in range(max_polls):
            if should_continue is not None and not should_continue():
                return None
            try:
                data = self.bridge.query_binary(protocol.WAV_DATA, timeout=0.5)
                if len(data) <= 4:
                    time.sleep(0.005)
                    continue
                raw_adc = parse_wav_data(data)
                voltage = adc_to_voltage(raw_adc, settings.v_per_div, settings.offset)
                time_axis = make_time_axis(
                    len(raw_adc), t_per_div,
                    trigger_sample=trigger_sample,
                )
                return WaveformData(
                    channel=ch,
                    raw_adc=raw_adc,
                    voltage=voltage,
                    time_axis=time_axis,
                    v_per_div=settings.v_per_div,
                    offset=settings.offset,
                    t_per_div=t_per_div,
                    probe_factor=settings.probe_factor,
                    timestamp=time.monotonic(),
                )
            except BridgeProtocolError:
                time.sleep(0.005)
                continue
            except BridgeTimeoutError:
                time.sleep(0.01)
                continue
        return None

    # -- Generic setting dispatcher ----------------------------------

    # Keys routed to concrete setters. Used by scripts and by the
    # automation layer; the GUI continues to call typed methods directly.
    _SETTING_DISPATCH: dict[str, str] = {
        # "channel.N.vdiv" is handled specially below (N is parsed).
        "timebase.tdiv": "set_tdiv",
        "timebase.position": "set_position",
        "trigger.level": "set_trigger_level",
        "trigger.source": "set_trigger_source",
        "trigger.slope": "set_trigger_slope",
        "trigger.sweep": "set_trigger_sweep",
        "trigger.coupling": "set_trigger_coupling",
        # Pulse-width (glitch) trigger
        "trigger.mode": "set_trigger_mode",
        "trigger.pulse.polarity": "set_trigger_pulse_polarity",
        "trigger.pulse.qualifier": "set_trigger_pulse_qualifier",
        "trigger.pulse.greater": "set_trigger_pulse_greater",
        "trigger.pulse.less": "set_trigger_pulse_less",
        "trigger.pulse.source": "set_trigger_pulse_source",
    }

    _CHANNEL_FIELD_DISPATCH: dict[str, str] = {
        "enabled": "set_channel_enabled",
        "vdiv": "set_vdiv",
        "offset": "set_offset",
        "coupling": "set_coupling",
        "bwlimit": "set_bwlimit",
        "probe": "set_probe",
    }

    def apply_setting(self, key: str, value: Any) -> None:
        ch_method = self._resolve_channel_setting(key)
        if ch_method is not None:
            method, ch = ch_method
            method(ch, value)
            return
        method_name = self._SETTING_DISPATCH.get(key)
        if method_name is None:
            raise KeyError(
                f"U2702ADriver: unknown setting {key!r}; "
                f"try one of {self.supported_settings()}",
            )
        getattr(self, method_name)(value)

    def _resolve_channel_setting(self, key: str):
        parts = key.split(".")
        if len(parts) != 3 or parts[0] != "channel":
            return None
        try:
            ch = int(parts[1])
        except ValueError:
            return None
        method_name = self._CHANNEL_FIELD_DISPATCH.get(parts[2])
        if method_name is None:
            return None
        return getattr(self, method_name), ch

    def read_setting(self, key: str) -> Any:
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "channel":
            try:
                ch = int(parts[1])
            except ValueError:
                raise KeyError(key) from None
            with self._lock:
                s = self._channels.get(ch, ChannelSettings())
                return getattr(s, {
                    "enabled": "enabled",
                    "vdiv": "v_per_div",
                    "offset": "offset",
                    "coupling": "coupling",
                    "bwlimit": "bw_limit",
                    "probe": "probe_factor",
                }.get(parts[2], parts[2]))
        with self._lock:
            return {
                "timebase.tdiv": self._t_per_div,
                "trigger.level": self._trigger_level,
                "trigger.slope": self._trigger_slope,
                "trigger.source": self._trigger_source,
            }.get(key)

    def supported_settings(self) -> tuple[str, ...]:
        keys: list[str] = list(self._SETTING_DISPATCH.keys())
        for ch in range(1, self.capabilities.num_channels + 1):
            for field in self._CHANNEL_FIELD_DISPATCH:
                keys.append(f"channel.{ch}.{field}")
        return tuple(keys)
