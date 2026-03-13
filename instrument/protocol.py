"""
SCPI Protocol Definitions for the U2702A

Command strings and response parsers. Based on reverse-engineered
protocol from USB captures (see SCPI_COMMANDS.md).

NOTE: The U2702A has a minimal SCPI implementation. Many standard
commands (WAV:PREAMBLE, MEAS:*, *RST, CHANNEL:PROBE) do NOT exist.
"""


# --- System / IEEE 488.2 ---

IDN = "*IDN?"
CLS = "*CLS"
OPC = "*OPC?"

# --- Acquisition Control ---
# NOTE: Leading colon is required!

RUN = ":RUN"
STOP = ":STOP"
SINGLE = ":SINGLE"

# --- Channel Configuration ---


def channel_display_query(ch):
    """Query channel display state. Returns '0' or '1'."""
    return f"CHANNEL{ch}:DISPLAY?"


def channel_display_set(ch, on):
    """Enable/disable channel display."""
    return f"CHANNEL{ch}:DISPLAY {'ON' if on else 'OFF'}"


def channel_scale_query(ch):
    """Query V/div. Returns scientific notation string."""
    return f"CHANNEL{ch}:SCALE?"


def channel_scale_set(ch, v_per_div):
    """Set V/div. Value in volts (e.g., 0.2 for 200mV/div)."""
    return f"CHANNEL{ch}:SCALE {v_per_div:.6E}"


def channel_offset_query(ch):
    """Query vertical offset (volts)."""
    return f"CHANNEL{ch}:OFFSET?"


def channel_offset_set(ch, offset):
    """Set vertical offset (volts)."""
    return f"CHANNEL{ch}:OFFSET {offset:.6E}"


def channel_coupling_query(ch):
    """Query coupling mode. Returns 'DC' or 'AC'."""
    return f"CHANNEL{ch}:COUPLING?"


def channel_coupling_set(ch, coupling):
    """Set coupling mode. Values: 'DC', 'AC'."""
    return f"CHANNEL{ch}:COUPLING {coupling}"


def channel_bwlimit_query(ch):
    """Query bandwidth limit. Returns '0' or '1'."""
    return f"CHANNEL{ch}:BWLIMIT?"


def channel_bwlimit_set(ch, on):
    """Enable/disable bandwidth limit."""
    return f"CHANNEL{ch}:BWLIMIT {'ON' if on else 'OFF'}"


# --- Timebase ---


def timebase_scale_query():
    """Query T/div."""
    return "TIM:SCAL?"


def timebase_scale_set(t_per_div):
    """Set T/div (seconds). Always followed by TIMEBASE:POS 0."""
    return f"TIM:SCAL {t_per_div:.6E}"


def timebase_position_query():
    """Query horizontal position."""
    return "TIMEBASE:POS?"


def timebase_position_set(position=0.0):
    """Set horizontal position (seconds). Usually 0."""
    return f"TIMEBASE:POS {position:.6E}"


def timebase_range_query():
    """Query time range (= 10 * T/div)."""
    return "TIM:RANG?"


def timebase_mode_query():
    """Query timebase mode. Returns 'MAIN'."""
    return "TIM:MODE?"


def timebase_ref_query():
    """Query reference point. Returns 'CENT'."""
    return "TIM:REF?"


# --- Trigger ---


def trigger_mode_query():
    """Query trigger type. Returns 'EDGE', 'GLIT', or 'TV'."""
    return "TRIGGER:MODE?"


def trigger_mode_set(mode):
    """Set trigger type. Values: 'EDGE', 'GLIT', 'TV'."""
    return f"TRIGGER:MODE {mode}"


def trigger_sweep_query():
    """Query sweep mode. Returns 'AUTO' or 'NORM'."""
    return "TRIGGER:SWEEP?"


def trigger_sweep_set(mode):
    """Set sweep mode. Values: 'AUTO', 'NORM'."""
    return f"TRIGGER:SWEEP {mode}"


def trigger_holdoff_query():
    """Query trigger holdoff (seconds)."""
    return "TRIGGER:HOLDOFF?"


def trigger_holdoff_set(holdoff):
    """Set trigger holdoff (seconds)."""
    return f"TRIGGER:HOLDOFF {holdoff:.6E}"


def trigger_nreject_query():
    """Query noise reject. Returns '0' (off)."""
    return "TRIGGER:NREJECT?"


def trigger_output_source_query():
    """Query trigger output source. Returns 'NONE'."""
    return "OUTPUT:TRIGGER:SOURCE?"


# --- Edge Trigger ---


def trigger_edge_source_query():
    """Query edge trigger source. Returns 'CHAN1', 'CHAN2', or 'EXT'."""
    return "TRIGGER:EDGE:SOURCE?"


def trigger_edge_source_set(source):
    """Set edge trigger source. Values: 'CHAN1', 'CHAN2', 'EXT'."""
    return f"TRIGGER:EDGE:SOURCE {source}"


def trigger_edge_level_query():
    """Query edge trigger level (volts)."""
    return "TRIGGER:EDGE:LEVEL?"


def trigger_edge_level_set(level):
    """Set edge trigger level (volts)."""
    return f"TRIGGER:EDGE:LEVEL {level:.6E}"


def trigger_edge_slope_query():
    """Query edge trigger slope. Returns 'POS', 'NEG', 'EITH', or 'ALT'."""
    return "TRIG:EDGE:SLOPE?"


def trigger_edge_slope_set(slope):
    """Set edge trigger slope. Values: 'POS', 'NEG', 'EITH', 'ALT'."""
    return f"TRIG:EDGE:SLOPE {slope}"


def trigger_edge_coupling_query():
    """Query edge trigger coupling. Returns 'DC', 'AC', 'LFR', or 'HFR'."""
    return "TRIGGER:EDGE:COUPLING?"


def trigger_edge_coupling_set(coupling):
    """Set edge trigger coupling. Values: 'DC', 'AC', 'LFR', 'HFR'."""
    return f"TRIGGER:EDGE:COUPLING {coupling}"


# --- Glitch (Pulse Width) Trigger ---


def trigger_glitch_polarity_query():
    return "TRIGGER:GLITCH:POLARITY?"


def trigger_glitch_polarity_set(polarity):
    return f"TRIGGER:GLITCH:POLARITY {polarity}"


def trigger_glitch_qualifier_query():
    return "TRIGGER:GLITCH:QUALIFIER?"


def trigger_glitch_qualifier_set(qualifier):
    """Values: 'LESS', 'GRE', 'RANG', 'OUTRANG'."""
    return f"TRIGGER:GLITCH:QUALIFIER {qualifier}"


def trigger_glitch_greater_query():
    return "TRIGGER:GLITCH:GRE?"


def trigger_glitch_less_query():
    return "TRIGGER:GLITCH:LESS?"


def trigger_glitch_range_query():
    return "TRIGGER:GLITCH:RANGE?"


# --- TV Trigger ---


def trigger_tv_mode_query():
    return "TRIGGER:TV:MODE?"


def trigger_tv_standard_query():
    return "TRIGGER:TV:STANDARD?"


def trigger_tv_line_query():
    return "TRIGGER:TV:LINE?"


def trigger_tv_polarity_query():
    return "TRIGGER:TV:POLARITY?"


# --- Waveform Data ---

WAV_DATA = "WAV:DATA?"


def wav_source_set(channel):
    """Select which channel's data WAV:DATA? returns.

    NOTE: Only the SET form works. WAV:SOUR? (query) does NOT exist.

    Args:
        channel: 1 or 2.
    """
    return f"WAV:SOUR CHAN{channel}"


# --- Acquisition Type ---

ACQ_TYPE = "ACQ:TYPE?"

# --- Function / Math ---

NOISE_FLOOR_QUERY = "FUNCTION:NOISEFLOOR?"
NOISE_FLOOR_OFF = "FUNCTION:NOISEFLOOR OFF"


# --- Initialization Sequence ---
# Captured from AMM startup. Order matters.
# Channel queries are built dynamically via build_init_sequence().

_INIT_PRE_CHANNELS = [
    CLS,
    ACQ_TYPE,                          # -> "NORM"
    "TIM:MODE?",                       # -> "MAIN"
    "TIMEBASE:POS?",                   # -> +0.00000000E+00
    "TIM:RANG?",                       # -> time range
    "TIM:REF?",                        # -> "CENT"
    "TIM:SCAL?",                       # -> time/div
    "TIMEBASE:POS 0.000000E+000",
    OPC,                               # -> 1
    NOISE_FLOOR_QUERY,                 # -> 0
    "TRIGGER:MODE?",                   # -> "EDGE"
    "TRIGGER:HOLDOFF?",
    "TRIGGER:SWEEP?",                  # -> "AUTO"
    "TRIGGER:NREJECT?",
    "OUTPUT:TRIGGER:SOURCE?",
    "TRIGGER:EDGE:SOURCE?",
    "TRIGGER:EDGE:LEVEL?",
    "TRIGGER:EDGE:COUPLING?",
    "TRIG:EDGE:SLOPE?",
    "TRIGGER:GLITCH:POLARITY?",
    "TRIGGER:GLITCH:QUALIFIER?",
    "TRIGGER:GLITCH:GRE?",
    "TRIGGER:GLITCH:LESS?",
    "TRIGGER:GLITCH:RANGE?",
    "TRIGGER:TV:MODE?",
    "TRIGGER:TV:STANDARD?",
    "TRIGGER:TV:LINE?",
    "TRIGGER:TV:POLARITY?",
]

_INIT_POST_CHANNELS = [
    "TRIGGER:SWEEP AUTO",
    OPC,                               # -> 1
    NOISE_FLOOR_OFF,
    "TRIG:EDGE:SLOPE POS",
]

_CHANNEL_QUERIES = [
    "OFFSET?", "SCALE?", "DISPLAY?", "BWLIMIT?", "COUPLING?",
]


def build_init_sequence(num_channels: int = 2) -> list[str]:
    """Build the full init sequence for the given number of channels."""
    seq = list(_INIT_PRE_CHANNELS)
    for ch in range(1, num_channels + 1):
        for q in _CHANNEL_QUERIES:
            seq.append(f"CHANNEL{ch}:{q}")
    seq.extend(_INIT_POST_CHANNELS)
    return seq


# Default sequence (backward compatible)
INIT_SEQUENCE = build_init_sequence(2)
