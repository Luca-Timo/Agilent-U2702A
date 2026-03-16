"""
Waveform data export — CSV, JSON, and NPZ formats with metadata.

Functions:
    export_csv(waveforms, measurements, path)   Write waveform data to CSV
    export_json(waveforms, measurements, path)  Write waveform data to JSON
    export_npz(waveforms, measurements, path)   Write waveform data to NPZ
"""

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np

from gui.theme import format_si
from processing.waveform import WaveformData


# Measurement keys for header formatting
_MEAS_KEYS = [
    ("Vpp", "vpp", "V"),
    ("Vmin", "vmin", "V"),
    ("Vmax", "vmax", "V"),
    ("Vrms", "vrms", "V"),
    ("Vmean", "vmean", "V"),
    ("Freq", "frequency", "Hz"),
    ("Period", "period", "s"),
    ("Rise", "rise_time", "s"),
    ("Fall", "fall_time", "s"),
]


def export_csv(
    waveforms: dict[int, WaveformData],
    measurements: dict[int, dict],
    path: str,
    apply_probe: bool = True,
):
    """Export waveform data to a CSV file with metadata header.

    Args:
        waveforms: Dict of channel → WaveformData (only enabled channels).
        measurements: Dict of channel → measurement results dict.
        path: Output file path.
        apply_probe: If True, multiply voltage by probe_factor (tip voltage).
    """
    if not waveforms:
        return

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Sort channels for consistent column order
    channels = sorted(waveforms.keys())

    with open(p, "w", newline="") as f:
        # --- Metadata header (comment lines) ---
        f.write("# Agilent U2702A — Waveform Export\n")
        f.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("#\n")

        # Per-channel settings
        for ch in channels:
            wf = waveforms[ch]
            probe_str = f"{wf.probe_factor:g}x" if wf.probe_factor != 1.0 else "1x"
            f.write(
                f"# CH{ch}: "
                f"V/div={format_si(wf.v_per_div, 'V')}, "
                f"Offset={format_si(wf.offset, 'V')}, "
                f"Probe={probe_str}, "
                f"T/div={format_si(wf.t_per_div, 's')}\n"
            )

        # Measurements summary
        if measurements:
            f.write("#\n")
            f.write("# Measurements:\n")
            for ch in channels:
                meas = measurements.get(ch, {})
                if not meas:
                    continue
                parts = []
                for label, key, unit in _MEAS_KEYS:
                    val = meas.get(key)
                    if val is not None:
                        parts.append(f"{label}={format_si(val, unit)}")
                duty = meas.get("duty_cycle")
                if duty is not None:
                    parts.append(f"Duty={duty:.1f}%")
                if parts:
                    f.write(f"# CH{ch}: {', '.join(parts)}\n")

        f.write("#\n")

        # --- CSV data ---
        writer = csv.writer(f)

        # Header row
        header = ["Time (s)"]
        for ch in channels:
            probe = waveforms[ch].probe_factor
            if apply_probe and probe != 1.0:
                header.append(f"CH{ch} (V, {probe:g}x)")
            else:
                header.append(f"CH{ch} (V)")
        writer.writerow(header)

        # Data rows — use first channel's time axis as reference
        ref_ch = channels[0]
        time_axis = waveforms[ref_ch].time_axis
        num_points = len(time_axis)

        for i in range(num_points):
            row = [f"{time_axis[i]:.9e}"]
            for ch in channels:
                wf = waveforms[ch]
                if i < len(wf.voltage):
                    v = wf.voltage[i]
                    if apply_probe:
                        v *= wf.probe_factor
                    row.append(f"{v:.6e}")
                else:
                    row.append("")
            writer.writerow(row)


def export_json(
    waveforms: dict[int, WaveformData],
    measurements: dict[int, dict],
    path: str,
    apply_probe: bool = True,
):
    """Export waveform data to a JSON file with metadata.

    Args:
        waveforms: Dict of channel → WaveformData (only enabled channels).
        measurements: Dict of channel → measurement results dict.
        path: Output file path.
        apply_probe: If True, multiply voltage by probe_factor (tip voltage).
    """
    if not waveforms:
        return

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    channels = sorted(waveforms.keys())
    ref_ch = channels[0]

    # Build channel data
    channel_data = {}
    for ch in channels:
        wf = waveforms[ch]
        voltage = wf.voltage.copy()
        if apply_probe:
            voltage = voltage * wf.probe_factor
        channel_data[f"CH{ch}"] = {
            "settings": {
                "v_per_div": wf.v_per_div,
                "offset": wf.offset,
                "t_per_div": wf.t_per_div,
                "probe_factor": wf.probe_factor,
            },
            "voltage": voltage.tolist(),
            "measurements": measurements.get(ch, {}),
        }

    data = {
        "instrument": "Agilent U2702A",
        "date": datetime.now().isoformat(),
        "time_axis": waveforms[ref_ch].time_axis.tolist(),
        "channels": channel_data,
    }

    with open(p, "w") as f:
        json.dump(data, f, indent=2)


def export_npz(
    waveforms: dict[int, WaveformData],
    measurements: dict[int, dict],
    path: str,
):
    """Export waveform data to a compressed NumPy archive (.npz).

    Stores raw scope-space voltage (no probe applied) for lossless round-trip
    and downstream signal analysis.

    Args:
        waveforms: Dict of channel -> WaveformData (only enabled channels).
        measurements: Dict of channel -> measurement results dict.
        path: Output file path.
    """
    if not waveforms:
        return

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    channels = sorted(waveforms.keys())
    ref_ch = channels[0]

    # Build metadata JSON
    meta_channels = {}
    for ch in channels:
        wf = waveforms[ch]
        meta_channels[str(ch)] = {
            "v_per_div": wf.v_per_div,
            "offset": wf.offset,
            "t_per_div": wf.t_per_div,
            "probe_factor": wf.probe_factor,
            "trigger_sample": wf.trigger_sample,
            "measurements": measurements.get(ch, {}),
        }

    metadata = {
        "instrument": "Agilent U2702A",
        "date": datetime.now().isoformat(),
        "channels": list(channels),
        "channel_settings": meta_channels,
    }

    # Build arrays dict for np.savez_compressed
    arrays: dict[str, np.ndarray] = {
        "time_axis": waveforms[ref_ch].time_axis,
        "metadata": np.array(json.dumps(metadata)),  # scalar string array
    }
    for ch in channels:
        wf = waveforms[ch]
        arrays[f"ch{ch}_voltage"] = wf.voltage          # raw scope-space
        arrays[f"ch{ch}_raw_adc"] = wf.raw_adc

    np.savez_compressed(p, **arrays)
