"""
Session save/load — JSON serialization of oscilloscope workspace state.

Functions:
    gather_state(win) -> dict    Collect all panel state into a dict
    apply_state(win, state)      Restore state from a dict into all panels
    save_to_file(state, path)    Write state dict to a JSON file
    load_from_file(path) -> dict Read state dict from a JSON file
"""

import json
from pathlib import Path

SESSION_VERSION = "0.8.3"

# Auto-save location
CONFIG_DIR = Path.home() / ".config" / "U2702A"
AUTO_SAVE_PATH = CONFIG_DIR / "last_session.json"


def default_state() -> dict:
    """Return the factory-default session state."""
    from gui.theme import NUM_CHANNELS, channel_color
    channels = {}
    for ch in range(1, NUM_CHANNELS + 1):
        channels[str(ch)] = {
            "enabled": ch == 1,
            "v_per_div": 1.0,
            "offset": 0.0,
            "coupling": "DC",
            "probe_factor": 1.0,
            "current_mode": False,
            "shunt_resistance": 1.0,
            "color": channel_color(ch),
        }
    return {
        "version": SESSION_VERSION,
        "channels": channels,
        "timebase": {"t_per_div": 0.001, "position": 0.0},
        "trigger": {
            "level": 0.0, "source": "CHAN1", "slope": "POS",
            "sweep": "AUTO", "coupling": "DC",
        },
        "cursors": {
            "mode": "off", "time": [0.0, 0.0],
            "volt": [0.0, 0.0], "channel": 1,
        },
        "display": {
            "measurements_visible": True,
            "enabled_measurements": ["Freq", "Period", "Vmax", "Vmin", "Vpp"],
            "dmm_mode": False,
            "dmm_measurement_mode": "DC",
            "dmm_hold": False,
            "dmm_relative": False,
            "dmm_range_locked": False,
            "knob_scroll": False,
            "averaging_count": 0,
            "split_view": False,
            "fft_enabled": False,
            "fft_source": 1,
            "fft_scale": "dbv",
            "fft_window": "hann",
            "math_enabled": False,
            "math_op": "add",
        },
        "window": {"geometry": [100, 100, 1440, 900]},
    }


def gather_state(win) -> dict:
    """Collect all GUI state from MainWindow into a JSON-serializable dict.

    Args:
        win: MainWindow instance.

    Returns:
        dict matching the session file schema.
    """
    from gui.theme import NUM_CHANNELS
    from gui.knob_widget import RotaryKnob

    # --- Channels ---
    channels = {}
    for ch in range(1, NUM_CHANNELS + 1):
        st = win._channel_panel.get_state(ch)
        channels[str(ch)] = {
            "enabled": st.enabled,
            "v_per_div": st.v_per_div,
            "offset": st.offset,
            "coupling": st.coupling,
            "probe_factor": st.probe_factor,
            "current_mode": st.current_mode,
            "shunt_resistance": st.shunt_resistance,
            "color": win._channel_colors.get(ch, ""),
            "inverted": win._channel_inverted.get(ch, False),
        }

    # --- Timebase ---
    timebase = {
        "t_per_div": win._timebase_panel.t_per_div,
        "position": win._timebase_panel.position,
    }

    # --- Trigger ---
    trigger = {
        "level": win._trigger_panel.level,
        "source": win._trigger_panel.source,
        "slope": win._trigger_panel.slope,
        "sweep": win._trigger_panel.sweep,
        "coupling": win._trigger_panel.coupling,
    }

    # --- Cursors ---
    cursors = {
        "mode": win._waveform._cursor_mode,
        "time": list(win._waveform._time_cursors),
        "volt": list(win._waveform._volt_cursors),
        "channel": win._cursor_channel,
    }

    # --- Display ---
    display = {
        "measurements_visible": win._utility_panel.measurements_visible,
        "enabled_measurements": win._measurement_bar.enabled_measurements,
        "dmm_mode": win._dmm_mode,
        "dmm_measurement_mode": win._dmm_widget.mode,
        "dmm_hold": win._hold_active,
        "dmm_relative": win._rel_active,
        "dmm_range_locked": win._range_locked,
        "knob_scroll": RotaryKnob._scroll_enabled,
        "averaging_count": win._utility_panel.averaging_count,
        "split_view": win._container.mode == "split",
        "fft_enabled": win._fft_enabled,
        "fft_source": win._fft_source,
        "fft_scale": win._fft_scale,
        "fft_window": win._fft_window,
        "math_enabled": win._math_enabled,
        "math_op": win._math_op,
    }

    # --- Window geometry ---
    geo = win.geometry()
    window = {
        "geometry": [geo.x(), geo.y(), geo.width(), geo.height()],
    }

    return {
        "version": SESSION_VERSION,
        "channels": channels,
        "timebase": timebase,
        "trigger": trigger,
        "cursors": cursors,
        "display": display,
        "window": window,
    }


def apply_state(win, state: dict, restore_geometry: bool = True):
    """Restore GUI state from a session dict into all MainWindow panels.

    Args:
        win: MainWindow instance.
        state: dict loaded from session JSON file.
        restore_geometry: If True, also restore window position/size.
    """
    from gui.theme import NUM_CHANNELS
    from gui.knob_widget import RotaryKnob

    if not state:
        return

    # --- Channels ---
    channels = state.get("channels", {})
    for ch_str, ch_data in channels.items():
        ch = int(ch_str)
        if ch < 1 or ch > NUM_CHANNELS:
            continue

        # Set channel panel state (handles UI widget updates)
        win._channel_panel.set_channel_state(
            ch,
            enabled=ch_data.get("enabled"),
            v_per_div=ch_data.get("v_per_div"),
            offset=ch_data.get("offset"),
            coupling=ch_data.get("coupling"),
            probe_factor=ch_data.get("probe_factor"),
            current_mode=ch_data.get("current_mode"),
            shunt_resistance=ch_data.get("shunt_resistance"),
        )

        # Sync waveform widget
        enabled = ch_data.get("enabled", False)
        win._waveform.set_channel_enabled(ch, enabled)
        win._measurement_bar.set_channel_visible(ch, enabled)
        win._dmm_widget.set_channel_visible(ch, enabled)

        offset = ch_data.get("offset", 0.0)
        win._waveform.set_channel_offset(ch, offset)

        probe = ch_data.get("probe_factor", 1.0)
        vdiv = ch_data.get("v_per_div", 1.0)
        win._waveform.set_channel_probe(ch, probe)
        win._waveform.set_channel_vdiv(ch, vdiv * probe)
        # Sync worker so incoming WaveformData.probe_factor is correct
        win.sig_set_probe.emit(ch, probe)

        current_mode = ch_data.get("current_mode", False)
        shunt = ch_data.get("shunt_resistance", 1.0)
        win._waveform.set_channel_current_mode(ch, current_mode, shunt)
        win._measurement_bar.set_channel_current_mode(ch, current_mode)
        win._dmm_widget.set_channel_current_mode(ch, current_mode)

        # Channel color
        color = ch_data.get("color")
        if color:
            win._channel_colors[ch] = color
            win._waveform.set_channel_color(ch, color)
            win._dmm_widget.set_channel_color(ch, color)

        # Channel invert
        inverted = ch_data.get("inverted", False)
        if inverted:
            win._channel_inverted[ch] = True
            win._channel_panel.set_channel_state(ch, inverted=True)
            win._waveform.set_channel_inverted(ch, True)

    # --- Timebase ---
    tb = state.get("timebase", {})
    tdiv = tb.get("t_per_div")
    if tdiv is not None:
        win._timebase_panel.set_tdiv(tdiv)
    pos = tb.get("position")
    if pos is not None:
        win._timebase_panel.set_position(pos)
        win._waveform.set_h_position(pos)

    # --- Trigger (source before level — level line depends on source channel) ---
    trig = state.get("trigger", {})
    if "source" in trig:
        win._trigger_panel.set_source(trig["source"])
        win._trigger_source = trig["source"]
        if trig["source"].startswith("CHAN"):
            src_ch = int(trig["source"][4:])
            win._waveform.set_trigger_source_channel(src_ch)
            src_offset = win._channel_panel.get_state(src_ch).offset
            win._waveform.set_trigger_source_offset(src_offset)
    if "slope" in trig:
        win._trigger_panel.set_slope(trig["slope"])
        win._waveform.set_trigger_slope(trig["slope"])
    if "sweep" in trig:
        win._trigger_panel.set_sweep(trig["sweep"])
    if "coupling" in trig:
        win._trigger_panel.set_coupling(trig["coupling"])
    if "level" in trig:
        win._trigger_panel.set_level(trig["level"])
        win._waveform.set_trigger_level(trig["level"])

    # --- Cursors ---
    cur = state.get("cursors", {})
    cursor_mode = cur.get("mode", "off")
    time_vals = cur.get("time", [0.0, 0.0])
    volt_vals = cur.get("volt", [0.0, 0.0])
    cursor_ch = cur.get("channel", 1)

    # Set positions before enabling mode (bypasses first-activation defaults)
    win._waveform._time_cursors = list(time_vals)
    win._waveform._volt_cursors = list(volt_vals)
    if time_vals != [0.0, 0.0]:
        win._waveform._time_cursors_placed = True
    if volt_vals != [0.0, 0.0]:
        win._waveform._volt_cursors_placed = True

    win._time_cursors = {1: time_vals[0], 2: time_vals[1]}
    win._volt_cursors = {1: volt_vals[0], 2: volt_vals[1]}
    win._cursor_channel = cursor_ch
    win._cursor_readout.set_channel(cursor_ch)

    win._waveform.set_cursor_mode(cursor_mode)
    win._utility_panel.set_cursor_mode(cursor_mode)
    win._cursor_readout.set_mode(cursor_mode)
    win._cursor_readout.setVisible(cursor_mode != "off")

    # Sync cursor channel mode (V/A + badge formatting)
    ch_state = win._channel_panel.get_state(cursor_ch)
    win._cursor_readout.set_current_mode(ch_state.current_mode)
    win._waveform.set_cursor_current_mode(ch_state.current_mode, channel=cursor_ch)

    # --- Display ---
    disp = state.get("display", {})
    meas_vis = disp.get("measurements_visible", True)
    win._utility_panel.set_measurements_visible(meas_vis)

    # Restore selected measurements
    enabled_meas = disp.get("enabled_measurements")
    if enabled_meas is not None:
        win._measurement_bar.set_enabled_measurements(enabled_meas)

    # Restore DMM mode (must come before measurement bar visibility)
    dmm_mode = disp.get("dmm_mode", False)
    if dmm_mode:
        win._utility_panel.set_dmm_mode(True)
    else:
        # Switch back to scope mode if currently in DMM mode
        if win._dmm_mode:
            win._utility_panel.set_dmm_mode(False)
        win._measurement_bar.setVisible(meas_vis)

    # Restore DMM measurement mode (DC / AC RMS / AC+DC RMS)
    dmm_meas_mode = disp.get("dmm_measurement_mode")
    if dmm_meas_mode:
        win._dmm_widget.set_mode(dmm_meas_mode)

    # Restore DMM extras (Hold / REL / Range Lock) — only when DMM mode active
    if dmm_mode:
        if disp.get("dmm_hold", False):
            win._utility_panel.set_hold(True)
        if disp.get("dmm_relative", False):
            win._utility_panel.set_relative(True)
        if disp.get("dmm_range_locked", False):
            win._utility_panel.set_range_lock(True)

    knob_scroll = disp.get("knob_scroll", True)
    RotaryKnob.set_scroll_enabled(knob_scroll)

    avg_count = disp.get("averaging_count", 0)
    win._utility_panel.set_averaging(avg_count)
    win._averager.set_count(avg_count)

    split_view = disp.get("split_view", False)
    win._container.set_layout_mode("split" if split_view else "combined")
    win._split_action.setChecked(split_view)

    # FFT state
    fft_window = disp.get("fft_window", "hann")
    win._fft_panel.set_window(fft_window)
    win._fft_window = fft_window
    fft_scale = disp.get("fft_scale", "dbv")
    win._fft_panel.set_scale(fft_scale)
    win._fft_scale = fft_scale
    fft_source = disp.get("fft_source", 1)
    win._fft_panel.set_source(fft_source)
    win._fft_source = fft_source
    fft_enabled = disp.get("fft_enabled", False)
    win._fft_panel.set_enabled(fft_enabled)
    win._fft_enabled = fft_enabled

    # Math state
    math_op = disp.get("math_op", "add")
    win._math_panel.set_operation(math_op)
    win._math_op = math_op
    math_enabled = disp.get("math_enabled", False)
    win._math_panel.set_enabled(math_enabled)
    win._math_enabled = math_enabled

    # --- Update waveform display axis scaling ---
    active_ch = win._channel_panel._active_channel
    ch_st = win._channel_panel.get_state(active_ch)
    effective = ch_st.v_per_div * ch_st.probe_factor
    current_tdiv = win._timebase_panel.t_per_div
    win._waveform.set_scales(effective, current_tdiv)

    # --- Window geometry ---
    if restore_geometry:
        window = state.get("window", {})
        geo = window.get("geometry")
        if geo and len(geo) == 4:
            win.setGeometry(geo[0], geo[1], geo[2], geo[3])


def save_to_file(state: dict, path: str):
    """Write session state dict to a JSON file.

    Creates parent directories if they do not exist.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(state, f, indent=2)


def load_from_file(path: str) -> dict:
    """Read session state dict from a JSON file.

    Returns empty dict if file does not exist or is malformed.
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
