"""
Acquisition worker — QObject running on a background QThread.

Handles SCPI streaming: init sequence, continuous/single waveform
acquisition, and instrument state management.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QThread, QCoreApplication

from instrument.serial_bridge import (
    SerialBridge, BridgeTimeoutError, BridgeCommandError,
    BridgeProtocolError, SerialBridgeError,
)
from instrument import protocol
from processing.waveform import (
    WaveformData, parse_wav_data, adc_to_voltage, make_time_axis,
    find_trigger_crossing,
)
from gui.theme import NUM_CHANNELS


@dataclass
class ChannelSettings:
    """Instrument-side settings for one channel."""
    enabled: bool = False
    v_per_div: float = 1.0
    offset: float = 0.0
    coupling: str = "DC"
    bw_limit: bool = False
    probe_factor: float = 1.0


class AcquisitionWorker(QObject):
    """Background worker for oscilloscope data acquisition.

    Lives on a QThread. Communicates with GUI via signals/slots.

    Signals:
        waveform_ready(WaveformData) — new waveform data for a channel
        init_complete(dict) — instrument initialization complete, parsed state
        status_changed(str) — bridge status change
        error_occurred(str) — error message
        fps_update(float) — current frames-per-second
    """

    waveform_ready = Signal(object)   # WaveformData
    init_complete = Signal(dict)
    status_changed = Signal(str)
    error_occurred = Signal(str)
    fps_update = Signal(float)
    trigger_status = Signal(str)    # ARMED, TRIG'D, AUTO, READY

    def __init__(self):
        super().__init__()
        self._bridge: Optional[SerialBridge] = None
        self._running = False
        self._mode = "stopped"  # "stopped", "continuous", "single"

        # Per-channel settings (updated from GUI)
        self._channels: dict[int, ChannelSettings] = {}
        self._enabled_channels: list[int] = [1]
        self._t_per_div: float = 1e-3

        # Trigger settings (for software trigger alignment)
        self._trigger_level: float = 0.0
        self._trigger_slope: str = "POS"
        self._trigger_source: str = "CHAN1"

        # FPS tracking
        self._frame_count = 0
        self._fps_timer = 0.0

    @property
    def bridge(self) -> Optional[SerialBridge]:
        return self._bridge

    @Slot(object)
    def set_bridge(self, bridge: SerialBridge):
        """Set the serial bridge connection (called after connection dialog)."""
        self._bridge = bridge
        if bridge and bridge.is_open:
            self.status_changed.emit(bridge.bridge_status)

    @Slot()
    def run_init_sequence(self):
        """Run the instrument initialization sequence and parse state."""
        if not self._bridge or not self._bridge.is_open:
            self.error_occurred.emit("Not connected")
            return

        state = {}
        try:
            init_seq = protocol.build_init_sequence(NUM_CHANNELS)
            for cmd in init_seq:
                if cmd.endswith("?"):
                    resp = self._bridge.query(cmd, timeout=2.0)
                    state[cmd] = resp.strip()
                else:
                    self._bridge.write(cmd, timeout=2.0)
                    state[cmd] = "OK"
                QThread.msleep(20)

            # Parse channel states
            parsed = self._parse_init_state(state)
            self.init_complete.emit(parsed)

        except SerialBridgeError as e:
            self.error_occurred.emit(f"Init failed: {e}")

    def _parse_init_state(self, raw: dict) -> dict:
        """Parse raw init sequence responses into structured state."""
        parsed = {
            "channels": {},
            "timebase": {},
            "trigger": {},
        }

        # Parse channel states
        for ch in range(1, NUM_CHANNELS + 1):
            ch_state = {}
            key = f"CHANNEL{ch}:SCALE?"
            if key in raw:
                try:
                    ch_state["v_per_div"] = float(raw[key])
                except ValueError:
                    pass

            key = f"CHANNEL{ch}:OFFSET?"
            if key in raw:
                try:
                    ch_state["offset"] = float(raw[key])
                except ValueError:
                    pass

            key = f"CHANNEL{ch}:DISPLAY?"
            if key in raw:
                ch_state["enabled"] = raw[key].strip() in ("1", "ON")

            key = f"CHANNEL{ch}:COUPLING?"
            if key in raw:
                ch_state["coupling"] = raw[key].strip()

            key = f"CHANNEL{ch}:BWLIMIT?"
            if key in raw:
                ch_state["bw_limit"] = raw[key].strip() in ("1", "ON")

            parsed["channels"][ch] = ch_state

        # Parse timebase
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

        # Parse trigger
        if "TRIGGER:EDGE:SOURCE?" in raw:
            parsed["trigger"]["source"] = raw["TRIGGER:EDGE:SOURCE?"].strip()
        if "TRIGGER:EDGE:LEVEL?" in raw:
            try:
                parsed["trigger"]["level"] = float(raw["TRIGGER:EDGE:LEVEL?"])
            except ValueError:
                pass
        if "TRIG:EDGE:SLOPE?" in raw:
            parsed["trigger"]["slope"] = raw["TRIG:EDGE:SLOPE?"].strip()
        if "TRIGGER:SWEEP?" in raw:
            parsed["trigger"]["sweep"] = raw["TRIGGER:SWEEP?"].strip()
        if "TRIGGER:EDGE:COUPLING?" in raw:
            parsed["trigger"]["coupling"] = raw["TRIGGER:EDGE:COUPLING?"].strip()

        # Store trigger settings locally for software trigger alignment
        if "level" in parsed["trigger"]:
            self._trigger_level = parsed["trigger"]["level"]
        if "slope" in parsed["trigger"]:
            self._trigger_slope = parsed["trigger"]["slope"]
        if "source" in parsed["trigger"]:
            self._trigger_source = parsed["trigger"]["source"]

        return parsed

    # --- Channel settings (from GUI) ---

    @Slot(int, bool)
    def set_channel_enabled(self, ch: int, enabled: bool):
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        self._channels[ch].enabled = enabled
        self._enabled_channels = [
            c for c, s in self._channels.items() if s.enabled
        ]

    @Slot(int, float)
    def set_vdiv(self, ch: int, value: float):
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        self._channels[ch].v_per_div = value

        # Send to instrument
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.channel_scale_set(ch, value))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set V/div failed: {e}")

    @Slot(int, float)
    def set_offset(self, ch: int, value: float):
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        self._channels[ch].offset = value

        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.channel_offset_set(ch, value))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set offset failed: {e}")

    @Slot(int, str)
    def set_coupling(self, ch: int, coupling: str):
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        self._channels[ch].coupling = coupling

        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.channel_coupling_set(ch, coupling))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set coupling failed: {e}")

    @Slot(int, bool)
    def set_bwlimit(self, ch: int, enabled: bool):
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        self._channels[ch].bw_limit = enabled

        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.channel_bwlimit_set(ch, enabled))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set BW limit failed: {e}")

    @Slot(int, float)
    def set_probe(self, ch: int, factor: float):
        if ch not in self._channels:
            self._channels[ch] = ChannelSettings()
        self._channels[ch].probe_factor = factor
        # Probe is software-only, no SCPI command

    @Slot(float)
    def set_tdiv(self, value: float):
        self._t_per_div = value
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.timebase_scale_set(value))
                self._bridge.write(protocol.timebase_position_set(0))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set T/div failed: {e}")

    @Slot(float)
    def set_position(self, value: float):
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.timebase_position_set(value))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set position failed: {e}")

    @Slot(float)
    def set_trigger_level(self, value: float):
        self._trigger_level = value
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.trigger_edge_level_set(value))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set trigger level failed: {e}")

    @Slot(str)
    def set_trigger_source(self, source: str):
        self._trigger_source = source
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.trigger_edge_source_set(source))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set trigger source failed: {e}")

    @Slot(str)
    def set_trigger_slope(self, slope: str):
        self._trigger_slope = slope
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.trigger_edge_slope_set(slope))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set trigger slope failed: {e}")

    @Slot(str)
    def set_trigger_sweep(self, mode: str):
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(protocol.trigger_sweep_set(mode))
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set trigger sweep failed: {e}")

    @Slot(str)
    def set_trigger_coupling(self, coupling: str):
        if self._bridge and self._bridge.is_open:
            try:
                self._bridge.write(
                    protocol.trigger_edge_coupling_set(coupling)
                )
            except SerialBridgeError as e:
                self.error_occurred.emit(f"Set trigger coupling failed: {e}")

    # --- Acquisition control ---

    @Slot()
    def start_continuous(self):
        """Start continuous acquisition."""
        self._mode = "continuous"
        self._running = True
        self._frame_count = 0
        self._fps_timer = time.monotonic()
        self._acquisition_loop()

    @Slot()
    def start_single(self):
        """Run a single acquisition."""
        self._mode = "single"
        self._running = True
        self._acquire_all_channels()
        self._running = False
        self._mode = "stopped"

    @Slot()
    def stop(self):
        """Stop acquisition."""
        self._running = False
        self._mode = "stopped"
        self.trigger_status.emit("READY")

    def _acquisition_loop(self):
        """Main continuous acquisition loop."""
        while self._running and self._mode == "continuous":
            self._acquire_all_channels()

            # FPS tracking
            self._frame_count += 1
            elapsed = time.monotonic() - self._fps_timer
            if elapsed >= 1.0:
                fps = self._frame_count / elapsed
                self.fps_update.emit(fps)
                self._frame_count = 0
                self._fps_timer = time.monotonic()

            # Process pending signals (e.g. stop()) so the thread's
            # event loop can deliver queued slot invocations.
            QCoreApplication.processEvents()
            QThread.msleep(1)

    def _acquire_all_channels(self):
        """Acquire waveforms for all enabled channels.

        Fires :SINGLE ONCE to trigger the scope, then reads each
        channel's data from that single capture. The scope captures
        ALL channels simultaneously — we just read them one by one.

        The trigger source channel is read first so we can detect
        the trigger crossing. All channels then use the same
        trigger_sample for time-axis alignment.
        """
        if not self._bridge or not self._bridge.is_open:
            self.error_occurred.emit("Not connected")
            self.stop()
            return

        try:
            # Enable all needed channels
            for ch in self._enabled_channels:
                self._bridge.write(
                    protocol.channel_display_set(ch, True), timeout=1.0
                )

            # Trigger ONE acquisition for all channels
            self.trigger_status.emit("ARMED")
            self._bridge.write(protocol.SINGLE, timeout=1.0)

            # Determine trigger source channel number (e.g. "CHAN1" → 1)
            trig_ch = None
            if self._trigger_source.startswith("CHAN"):
                try:
                    trig_ch = int(self._trigger_source[4:])
                except ValueError:
                    trig_ch = None

            # Order channels: trigger source first (so we find the
            # crossing before building time axes for other channels).
            # If trigger source is not enabled, still read it for
            # trigger detection but don't emit its waveform.
            ordered = list(self._enabled_channels)
            trig_ch_hidden = False
            if trig_ch is not None and trig_ch not in ordered:
                ordered.insert(0, trig_ch)
                trig_ch_hidden = True  # Read for trigger only
            elif trig_ch in ordered:
                ordered.remove(trig_ch)
                ordered.insert(0, trig_ch)

            trigger_sample = None  # shared across all channels

            for i, ch in enumerate(ordered):
                if not self._running:
                    break

                try:
                    waveform = self._read_channel_data(
                        ch, poll=(i == 0),
                        trigger_sample=trigger_sample,
                    )
                    if waveform:
                        # On the trigger source channel, detect the
                        # crossing and remember it for other channels.
                        if ch == trig_ch and trigger_sample is None:
                            # Adjust trigger level by channel offset —
                            # voltage data has offset baked in, so the
                            # crossing level must match.
                            adjusted_level = (self._trigger_level
                                              + waveform.offset)
                            trigger_sample = find_trigger_crossing(
                                waveform.voltage,
                                adjusted_level,
                                self._trigger_slope,
                            )
                            if trigger_sample is not None:
                                self.trigger_status.emit("TRIG'D")
                                waveform.trigger_sample = trigger_sample
                                # Rebuild this channel's time axis with
                                # the detected trigger position.
                                waveform.time_axis = make_time_axis(
                                    len(waveform.raw_adc),
                                    self._t_per_div,
                                    trigger_sample=trigger_sample,
                                )
                            else:
                                self.trigger_status.emit("AUTO")

                        # Only emit waveform for enabled (visible) channels
                        if not (ch == trig_ch and trig_ch_hidden):
                            self.waveform_ready.emit(waveform)
                except SerialBridgeError as e:
                    self.error_occurred.emit(f"CH{ch} read failed: {e}")

        except SerialBridgeError as e:
            self.error_occurred.emit(f"Acquisition failed: {e}")

    def _read_channel_data(self, ch: int, poll: bool = True,
                           trigger_sample: int | None = None) -> Optional[WaveformData]:
        """Read waveform data for one channel from the current capture.

        Args:
            ch: Channel number.
            poll: If True, poll WAV:DATA? until data is ready (for first
                  channel after :SINGLE). If False, data should already be
                  available (subsequent channels from same capture).
        """
        settings = self._channels.get(ch, ChannelSettings())

        # Select channel source
        self._bridge.write(protocol.wav_source_set(ch), timeout=1.0)

        # Poll WAV:DATA? — returns "00" until ready, then full data
        max_polls = 50 if poll else 10
        for _ in range(max_polls):
            if not self._running:
                return None

            try:
                data = self._bridge.query_binary(
                    protocol.WAV_DATA, timeout=0.5
                )

                # Check for "00" (not ready) — short data
                if len(data) <= 4:
                    QThread.msleep(5)
                    continue

                # Got real waveform data
                raw_adc = parse_wav_data(data)
                voltage = adc_to_voltage(
                    raw_adc,
                    settings.v_per_div,
                    settings.offset,
                )

                # Build time axis — if trigger_sample is known
                # (from the trigger source channel), all channels
                # use it so they stay aligned.
                time_axis = make_time_axis(
                    len(raw_adc), self._t_per_div,
                    trigger_sample=trigger_sample,
                )

                return WaveformData(
                    channel=ch,
                    raw_adc=raw_adc,
                    voltage=voltage,
                    time_axis=time_axis,
                    v_per_div=settings.v_per_div,
                    offset=settings.offset,
                    t_per_div=self._t_per_div,
                    probe_factor=settings.probe_factor,
                    timestamp=time.monotonic(),
                )

            except BridgeProtocolError:
                # Got text response instead of binary — "00" as text
                QThread.msleep(5)
                continue
            except BridgeTimeoutError:
                QThread.msleep(10)
                continue

        return None  # Timed out waiting for data
