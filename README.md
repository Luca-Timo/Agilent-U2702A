# Agilent U2702A Oscilloscope — macOS Desktop App

A macOS desktop application for the Agilent U2702A USB oscilloscope, built with PySide6 and PyQtGraph. Uses an ESP32-S3 as a USB bridge to bypass Apple Silicon USB driver limitations.

## Current Version: 0.8.2-alpha

### Features
- Real-time dual-channel waveform display with dark theme
- Keysight-inspired front panel layout (graph left, controls right)
- Custom rotary knobs (drag to adjust, click to enter exact value)
- Per-channel V/div, offset, coupling, and probe controls
- Horizontal T/div and position controls
- Edge trigger with level, source, slope, sweep, and coupling
- Software trigger alignment (trigger edge at center marker)
- Live measurements: Vpp, Vmin, Vmax, Vrms, Vmean, Freq, Period, Rise, Fall, Duty
- Measurement toggle buttons with per-channel readouts
- Cursor system (time, voltage, or both) with drag-to-position and readout bar
- Measurement click-to-cursor: click a measurement value to set cursors at key positions
- Measurement hover highlights on waveform
- Probe system: 1x / 10x / 100x / 1000x / Custom with probe badges on GND markers
- Probe compensation guidance dialog
- Digital multimeter mode (DC, AC RMS, AC+DC RMS) with large readout
- Current measurement mode (I = V/R via shunt resistor)
- DMM Hold, Relative (delta), and Range Lock
- Session save/load (JSON), auto-save on exit, auto-restore on startup
- Recent Sessions menu, QSettings persistence
- Export waveform data to CSV or JSON (with metadata + measurements)
- Export graph as PNG (dark/light) or PDF (A4 landscape)
- Unified Export dialog with Data and Graph tabs
- Drag-to-zoom with Cmd+Z undo
- Per-channel GND markers, trigger level indicator, trigger position marker
- Connection dialog with CP2102N auto-detection
- SCPI Tester tool (shared connection)
- Settings dialog (channel colors, probe attenuation, knob scroll toggle)

## Architecture

```
Mac (Python/PySide6)  <--  Serial (2Mbps)  -->  ESP32-S3  <--  USB Host  -->  U2702A
       GUI + Processing         CP2102N UART         Firmware          USBTMC
```

### Why ESP32-S3-DevKitC-1?
The ESP32-S3-DevKitC-1 was chosen because it has **two USB connectors**:

| Connector | Label on PCB | Connects to | Purpose |
|-----------|-------------|-------------|---------|
| **USB** (top) | USB | Computer (Mac) | CP2102N UART bridge — serial communication at 2 Mbps |
| **USB OTG** (bottom) | USB OTG | U2702A oscilloscope | Native USB Host — boots scope + USBTMC data transfer |

The U2702A boot-mode firmware violates USB 2.0 spec (no config descriptor). macOS Apple Silicon's USB stack permanently blocks the device after the first timeout. The ESP32-S3 acts as a USB-to-serial bridge, completely bypassing macOS USB.

### Three-Layer Design
1. **`instrument/`** — Hardware communication (serial bridge, SCPI protocol)
2. **`processing/`** — Signal analysis (ADC-to-voltage, measurements, trigger detection)
3. **`gui/`** — PySide6 display (waveform, controls, panels)

## Hardware Setup

### Prerequisites
- **ESP32-S3-DevKitC-1** (~$8) with firmware flashed (see `firmware/`)
- **Agilent U2702A** oscilloscope
- **USB-A to Micro-USB OTG cable** (to connect scope to ESP32 USB OTG port)
- **USB-C cable** (to connect ESP32 USB port to Mac)
- **Wire wrap / solder bridge** between the two USB VCC pins (see below)

### VCC Wire Wrap (Required!)
The ESP32-S3-DevKitC-1 has two separate USB connectors with independent power rails. The U2702A requires 5V power from the USB Host (ESP32 OTG port) to boot. By default, the OTG port does not supply 5V.

**You must connect the VCC (5V) pin from the CP2102N USB connector to the VCC pin of the USB OTG connector** with a short wire wrap or solder bridge. This routes the Mac's USB 5V power through to the scope.

```
  ESP32-S3-DevKitC-1
  ┌──────────────────┐
  │   [USB] ← to Mac │  ← CP2102N UART (serial data + 5V power source)
  │     VCC ─────┐   │
  │              wire │  ← Wire wrap: connect the two VCC pins
  │     VCC ─────┘   │
  │ [USB OTG] ← to   │  ← Native USB Host (USBTMC to scope)
  │     U2702A scope  │
  └──────────────────┘
```

### Connection Diagram
```
  ┌─────────┐    USB-C     ┌────────────────┐   USB OTG    ┌───────────┐
  │   Mac   │ ──────────── │  ESP32-S3      │ ──────────── │  U2702A   │
  │ (macOS) │   2 Mbps     │  DevKitC-1     │   USBTMC     │  Scope    │
  │         │   UART       │                │   USB Host   │           │
  └─────────┘              └────────────────┘              └───────────┘
       ↑                     ↑           ↑                      ↑
    python3 gui/main.py    USB port    USB OTG port         Micro-USB
                          (to Mac)    (to scope)
```

### Software Prerequisites
- Python 3.11+
- macOS (tested on Apple Silicon)

### Install Dependencies
```bash
pip install PySide6 pyqtgraph pyserial numpy
```

### Run
```bash
python3 gui/main.py
```

The connection dialog opens automatically. Select the CP2102N serial port and click Connect.

## Project Structure

```
gui/
    main.py                 # Entry point
    main_window.py          # Main oscilloscope window, signal wiring
    waveform_widget.py      # PyQtGraph plot, graticule, markers, cursors
    channel_panel.py        # Per-channel Keysight-style columns
    timebase_panel.py       # Horizontal T/div + Position
    trigger_panel.py        # Trigger controls
    measurement_bar.py      # Measurement toggle buttons + readouts
    acquisition_worker.py   # QThread SCPI streaming + trigger alignment
    knob_widget.py          # Custom rotary knob (drag + click popup)
    connection_dialog.py    # Serial port connection dialog
    settings_dialog.py      # Colors, probes, knob scroll
    utility_panel.py        # Autoscale, measurements, cursor mode, DMM
    cursor_readout.py       # Cursor readout panel (delta T, delta V)
    export_dialog.py        # Unified export (CSV/JSON + PNG/PDF graph)
    probe_comp_dialog.py    # Probe compensation guidance
    theme.py                # Dark theme, SI formatting, channel colors
    scpi_tester.py          # SCPI command tester tool
    session.py              # Session save/load/restore

instrument/
    serial_bridge.py        # Thread-safe serial bridge client
    protocol.py             # SCPI command definitions (61 commands)

processing/
    waveform.py             # WaveformData, ADC conversion, trigger detection
    measurements.py         # Vpp, Vrms, frequency, rise/fall, duty cycle
    autoscale.py            # Auto-range V/div, T/div, offset
    export.py               # CSV and JSON export functions

firmware/
    src/main.c              # ESP32-S3 firmware entry point
    src/u2702a_boot.c       # HCD boot sequence (PID 0x2818 → 0x2918)
    src/usb_host.c          # USB Host daemon + client tasks
    src/usbtmc.c            # USBTMC bulk transfer layer
    src/serial_bridge.c     # UART command dispatch
```

## Version History

See [VERSIONING.md](VERSIONING.md) for the full roadmap and feature checklist.

| Version | Status | Description |
|---------|--------|-------------|
| 0.1.x | Complete | Foundation: ESP32 bridge, SCPI tester, serial client |
| 0.2.x | Complete | Oscilloscope GUI: controls, waveforms, basic measurements |
| 0.3.x | Complete | Trigger system: edge trigger, modes, drag-to-zoom |
| 0.4.x | Complete | Measurements: rise/fall, duty cycle, cursors |
| 0.5.x | Complete | Probe system: 1x-1000x, custom, compensation |
| 0.6.x | Complete | Multimeter mode: DMM display, current measurement |
| 0.7.x | Complete | Session files: save/load/restore, auto-save |
| 0.8.x | Current | Export: CSV, JSON, PNG, PDF graph rendering |
| 1.0.0 | Planned | Protocol decoders, light theme, .app bundle |

## Status & Roadmap

> **This project is under active development.** Expect breaking changes between alpha versions.

The current focus is data export and graph rendering (0.8.x). Upcoming milestones:

| Milestone | Goal |
|-----------|------|
| **0.8.x** — Export & Data | CSV/JSON export, PNG/PDF graph, waveform averaging, reference traces |
| **1.0.0** — Release | Protocol decoders (UART, SPI, I2C), keyboard shortcuts, light theme, .app bundle |

**Post-1.0 ideas:** FFT/math functions, XY mode, persistence display, network/LAN bridge, mask testing, plugin system for other oscilloscopes.

See [VERSIONING.md](VERSIONING.md) for the full feature checklist.

## Contributing

Contributions are welcome! The modular three-layer architecture makes it possible to add support for other oscilloscopes by implementing the instrument interface. See [VERSIONING.md](VERSIONING.md) for the modular architecture requirements.

## License

This project is licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE) for details.

Copyright (C) 2026 Luca Bresch
