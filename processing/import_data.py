"""
Waveform data import — CSV, JSON, and NPZ formats.

All parsers return a common dict structure:
    {
        "time_axis": np.ndarray,
        "channels": {
            1: {
                "voltage": np.ndarray,    # scope-space (no probe applied)
                "raw_adc": np.ndarray | None,
                "v_per_div": float,
                "offset": float,
                "t_per_div": float,
                "probe_factor": float,
                "trigger_sample": int | None,
                "measurements": dict | None,
            },
            ...
        }
    }
"""

import csv
import json
import re
from pathlib import Path

import numpy as np


def import_file(path: str) -> dict:
    """Auto-detect format by extension and import."""
    ext = Path(path).suffix.lower()
    if ext == ".npz":
        return import_npz(path)
    elif ext == ".json":
        return import_json(path)
    elif ext == ".csv":
        return import_csv(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def import_npz(path: str) -> dict:
    """Import waveform data from a compressed NumPy archive."""
    data = np.load(path, allow_pickle=False)

    metadata = json.loads(str(data["metadata"]))
    time_axis = data["time_axis"]
    ch_settings = metadata.get("channel_settings", {})

    channels = {}
    for ch in metadata["channels"]:
        s = ch_settings.get(str(ch), {})
        voltage = data.get(f"ch{ch}_voltage")
        raw_adc = data.get(f"ch{ch}_raw_adc")
        if voltage is None:
            continue
        channels[int(ch)] = {
            "voltage": voltage,
            "raw_adc": raw_adc,
            "v_per_div": s.get("v_per_div", 1.0),
            "offset": s.get("offset", 0.0),
            "t_per_div": s.get("t_per_div", 1e-3),
            "probe_factor": s.get("probe_factor", 1.0),
            "trigger_sample": s.get("trigger_sample"),
            "measurements": s.get("measurements"),
        }

    return {"time_axis": time_axis, "channels": channels}


def import_json(path: str) -> dict:
    """Import waveform data from a JSON file.

    JSON stores probe-adjusted voltage, so we divide by probe_factor
    to recover scope-space voltage.
    """
    with open(path) as f:
        data = json.load(f)

    time_axis = np.array(data["time_axis"], dtype=np.float64)

    channels = {}
    for key, ch_data in data.get("channels", {}).items():
        # Parse channel number from "CH1", "CH2", etc.
        match = re.match(r"CH(\d+)", key)
        if not match:
            continue
        ch = int(match.group(1))

        s = ch_data.get("settings", {})
        probe = s.get("probe_factor", 1.0)
        voltage = np.array(ch_data["voltage"], dtype=np.float64)

        # Recover scope-space voltage (JSON stores probe-adjusted)
        if probe != 0 and probe != 1.0:
            voltage = voltage / probe

        channels[ch] = {
            "voltage": voltage,
            "raw_adc": None,
            "v_per_div": s.get("v_per_div", 1.0),
            "offset": s.get("offset", 0.0),
            "t_per_div": s.get("t_per_div", 1e-3),
            "probe_factor": probe,
            "trigger_sample": None,
            "measurements": ch_data.get("measurements"),
        }

    return {"time_axis": time_axis, "channels": channels}


def import_csv(path: str) -> dict:
    """Import waveform data from a CSV file with metadata header.

    CSV stores probe-adjusted voltage when probe != 1x (indicated by column
    header like "CH1 (V, 10x)"). We divide by the probe factor to recover
    scope-space voltage.
    """
    p = Path(path)
    header_comments = []
    data_lines = []

    with open(p, newline="") as f:
        for line in f:
            if line.startswith("#"):
                header_comments.append(line.rstrip("\n"))
            else:
                data_lines.append(line)

    # Parse per-channel settings from header comments
    # Format: "# CH1: V/div=1.00 V, Offset=0.00 V, Probe=10x, T/div=1.00 ms"
    ch_settings: dict[int, dict] = {}
    for line in header_comments:
        m = re.match(
            r"#\s*CH(\d+):\s*V/div=([^,]+),\s*Offset=([^,]+),"
            r"\s*Probe=([^,]+),\s*T/div=(.+)",
            line,
        )
        if m:
            ch = int(m.group(1))
            ch_settings[ch] = {
                "v_per_div": _parse_si(m.group(2).strip()),
                "offset": _parse_si(m.group(3).strip()),
                "probe_factor": _parse_probe(m.group(4).strip()),
                "t_per_div": _parse_si(m.group(5).strip()),
            }

    # Parse CSV data
    reader = csv.reader(data_lines)
    header = next(reader, None)
    if not header:
        raise ValueError("CSV file has no data header row")

    # Detect channels and probe factors from column headers
    # "CH1 (V)" or "CH1 (V, 10x)"
    col_channels: list[tuple[int, float]] = []  # (ch_number, probe_factor)
    for col in header[1:]:
        m = re.match(r"CH(\d+)\s*\(V(?:,\s*(\d+(?:\.\d+)?)x)?\)", col)
        if m:
            ch = int(m.group(1))
            probe = float(m.group(2)) if m.group(2) else 1.0
            col_channels.append((ch, probe))

    if not col_channels:
        raise ValueError("No channel columns found in CSV header")

    # Read data rows
    time_list: list[float] = []
    voltage_lists: dict[int, list[float]] = {ch: [] for ch, _ in col_channels}

    for row in reader:
        if not row or not row[0].strip():
            continue
        time_list.append(float(row[0]))
        for i, (ch, _) in enumerate(col_channels):
            idx = i + 1
            if idx < len(row) and row[idx].strip():
                voltage_lists[ch].append(float(row[idx]))

    time_axis = np.array(time_list, dtype=np.float64)

    channels = {}
    for ch, col_probe in col_channels:
        voltage = np.array(voltage_lists[ch], dtype=np.float64)

        # Use settings from header comments if available, else from column
        s = ch_settings.get(ch, {})
        probe = s.get("probe_factor", col_probe)

        # CSV stores probe-adjusted voltage — recover scope-space
        if probe != 0 and probe != 1.0:
            voltage = voltage / probe

        channels[ch] = {
            "voltage": voltage,
            "raw_adc": None,
            "v_per_div": s.get("v_per_div", 1.0),
            "offset": s.get("offset", 0.0),
            "t_per_div": s.get("t_per_div", 1e-3),
            "probe_factor": probe,
            "trigger_sample": None,
            "measurements": None,
        }

    return {"time_axis": time_axis, "channels": channels}


# --- SI prefix parser ---

_SI_PREFIXES = {
    "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "\u00b5": 1e-6,
    "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}


def _parse_si(text: str) -> float:
    """Parse an SI-formatted value like '1.00 mV' or '500 us'."""
    text = text.strip()
    # Remove trailing unit letters (V, s, Hz, A, etc.)
    text = re.sub(r"[VsHzAa]+$", "", text).strip()
    if not text:
        return 0.0

    # Check last char for SI prefix
    if text[-1] in _SI_PREFIXES:
        return float(text[:-1]) * _SI_PREFIXES[text[-1]]
    return float(text)


def _parse_probe(text: str) -> float:
    """Parse probe string like '10x' or '1x'."""
    m = re.match(r"(\d+(?:\.\d+)?)x", text)
    return float(m.group(1)) if m else 1.0
