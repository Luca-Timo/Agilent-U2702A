# Agilent U2702A Oscilloscope — macOS Desktop App

A macOS desktop application for the Agilent U2702A USB oscilloscope, built with PySide6 and PyQtGraph. Uses an ESP32-S3 as a USB bridge to bypass Apple Silicon USB driver limitations.

## Current Version: 0.2.3-alpha

### Features
- Real-time dual-channel waveform display with dark theme
- Keysight-inspired front panel layout (graph left, controls right)
- Custom rotary knobs (drag to adjust, click to enter exact value)
- Per-channel V/div, offset, coupling, and probe controls
- Horizontal T/div and position controls
- Edge trigger with level, source, slope, sweep, and coupling
- Software trigger alignment (trigger edge at center marker)
- Live measurements: Vpp, Vmin, Vmax, Vrms, Vmean, Freq, Period
- Measurement toggle buttons (select which measurements to display)
- Per-channel GND/0V markers on Y-axis
- Trigger level indicator (dashed line + right-edge badge)
- Trigger position marker on X-axis
- Connection dialog with auto-detection of CP2102N serial port
- SCPI Tester tool (Tools menu, shared connection)
- Settings dialog (channel colors, probe attenuation)

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
    main_window.py          # Main oscilloscope window
    waveform_widget.py      # PyQtGraph plot + markers
    channel_panel.py        # Per-channel controls (Keysight-style columns)
    timebase_panel.py       # Horizontal T/div + Position
    trigger_panel.py        # Trigger controls
    measurement_bar.py      # Measurement buttons + readouts
    acquisition_worker.py   # QThread SCPI streaming + trigger alignment
    knob_widget.py          # Custom rotary knob widget
    connection_dialog.py    # Serial port connection
    settings_dialog.py      # Colors, probes
    theme.py                # Dark theme, colors, formatting
    scpi_tester.py          # SCPI command tester

instrument/
    serial_bridge.py        # Thread-safe serial bridge client
    protocol.py             # SCPI command definitions (61 commands)

processing/
    waveform.py             # WaveformData, ADC conversion, trigger detection
    measurements.py         # Vpp, Vrms, frequency, etc.

firmware/
    src/main.c              # ESP32-S3 firmware entry point
    src/u2702a_boot.c       # HCD boot sequence
    src/usb_host.c          # USB Host tasks
    src/usbtmc.c            # USBTMC transport
    src/serial_bridge.c     # UART command dispatch
```

## Version History

See [VERSIONING.md](VERSIONING.md) for the full roadmap.

| Version | Status | Description |
|---------|--------|-------------|
| 0.1.x | Complete | Foundation: ESP32 bridge, SCPI tester, serial client |
| 0.2.x | Current | Oscilloscope GUI: controls, waveforms, measurements |
| 0.3.x | Planned | Advanced trigger system |
| 0.4.x | Planned | Measurements and math |
| 1.0.0 | Planned | Feature-complete release |

## Status & Roadmap

> **This project is under active development.** Expect breaking changes between alpha versions.

The current focus is building a fully functional oscilloscope GUI (0.2.x). Upcoming milestones:

| Milestone | Goal |
|-----------|------|
| **0.3.x** — Trigger System | Trigger modes (Auto/Normal/Single), pulse width trigger, trigger status |
| **0.4.x** — Measurements & Math | Rise/fall time, duty cycle, cursor measurements, FFT |
| **0.5.x** — Probe & Calibration | Per-probe config (1:1, 1:10, custom), compensation check |
| **0.6.x** — Multimeter Mode | Large digital voltage/frequency display, min/max tracking |
| **0.7.x** — Session Files | Save/load scope setups, auto-restore last session |
| **0.8.x** — Export & Data | CSV/NumPy export, screenshots, waveform averaging, reference traces |
| **1.0.0** — Release | Protocol decoders (UART, SPI, I2C), keyboard shortcuts, light theme, .app bundle |

**Post-1.0 ideas:** XY mode, persistence display, network/LAN bridge, mask testing, plugin system for other oscilloscopes.

See [VERSIONING.md](VERSIONING.md) for the full feature checklist.

## Contributing

Contributions are welcome! The modular three-layer architecture makes it possible to add support for other oscilloscopes by implementing the instrument interface. See [VERSIONING.md](VERSIONING.md) for the modular architecture requirements.

## License

This project is licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE) for details.

Copyright (C) 2026 Luca Bresch
