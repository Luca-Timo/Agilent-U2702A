# Project Knowledge: U2702A macOS Oscilloscope GUI

> Critical information that must not be forgotten. Reference this file before making decisions.
> Last updated: 2026-03-04

---

## Project Goal
Build a working GUI application on macOS to use the Agilent/Keysight U2702A USB oscilloscope with full scope functionality: waveform display, measurements, RMS calculations, probe calibration, and 1:1/1:10 probe compensation.

---

## Hard Constraints

### Device Constraints
- U2702A is **discontinued** (June 2024), 5 years support remaining
- USB 2.0 only (480 Mbit/s) -- no LAN, no GPIB
- 8-bit vertical resolution (256 levels)
- 2 channels only, no digital channels
- Requires external +12 VDC, 2 A power supply
- USB VID: `0x0957`, PID: `0x2918` (normal), `0x2818` (firmware update mode)

### Software Constraints
- **No official macOS support exists** -- we are building something that doesn't exist yet
- **No documented SCPI command set** -- must sniff via IO Monitor or reverse engineer
- **IVI-COM driver is Windows-only** -- cannot use directly on Mac
- Device may require Windows "jump-start" before responding on other platforms
- python-usbtmc has known pipe errors with this device

### Our Constraints
- Target: macOS (Apple Silicon and Intel)
- Language: Python 3.10+
- GUI: **PySide6** (Qt6) -- NOT PyQt5
- Plotting: PyQtGraph (for 1000+ FPS real-time waveform display)
- No NI-VISA dependency (use pyvisa-py backend)

---

## Critical Technical Facts

### 1. Undocumented SCPI Commands Exist
The device DOES respond to SCPI commands internally. Keysight never documented them, but they can be captured using IO Monitor while running Agilent Measurement Manager. This is confirmed by community members who successfully used sniffed commands in MATLAB and C++.

**This is the foundation of our approach.**

### 2. USB Communication Stack
```
Our App (PySide6 GUI)
    |
PyVISA (instrument abstraction)
    |
pyvisa-py (pure Python VISA backend)
    |
PyUSB (USB abstraction)
    |
libusb (native USB library, installed via brew)
    |
macOS USB subsystem
    |
U2702A hardware
```

### 3. Known Working Communication Path (Windows)
```
AMM / BenchVue / Custom App
    |
IVI-COM Driver (Windows DLL)
    |
VISA (NI-VISA or Keysight VISA)
    |
USBTMC-USB488 protocol
    |
U2702A hardware
```

### 4. Probe Compensation
- 1:1 probe: Direct measurement, no scaling needed
- 1:10 probe: Multiply measured voltage by 10
- Probe compensation affects vertical scale display and measurement calculations
- Standard calibration signal: 1 kHz square wave (typical for probe comp output)

### 5. RMS Calculation
```python
import numpy as np
rms = np.sqrt(np.mean(waveform_data ** 2))
```
- For AC-coupled: subtract DC offset first
- For windowed RMS: apply window function before calculation

---

## Architecture Decisions (Locked In)

| Decision | Choice | Reason |
|---|---|---|
| GUI Framework | PySide6 (Qt6) | User preference, modern, well-maintained |
| Plotting | PyQtGraph | 1000+ FPS, Qt-native, oscilloscope-grade |
| VISA Backend | pyvisa-py | No NI-VISA dependency, pure Python |
| USB Library | PyUSB + libusb | Cross-platform, brew-installable |
| Data Processing | NumPy + SciPy | Standard, fast, proven |
| Signal Processing | SciPy.signal + SciPy.fft | FFT, filtering, windowing |

---

## Phase Plan

> See VERSIONING.md for full staged feature plan (0.1.x-alpha through 1.0.0).

### Phase 0: Protocol Discovery (MUST DO FIRST)
- Set up Windows VM with AMM + IO Library Suite
- Use IO Monitor to capture ALL SCPI commands
- Document: init sequence, channel config, trigger setup, acquisition, data transfer
- Test captured commands via PyVISA on Windows first

### 0.1.x-alpha: Foundation & Connection
### 0.2.x-alpha: Controls & Scaling
### 0.3.x-alpha: Trigger System
### 0.4.x-alpha: Measurements & Math
### 0.5.x-alpha: Probe & Calibration
### 0.6.x-alpha: Multimeter Mode
### 0.7.x-alpha: Session Files & Persistence
### 0.8.x-alpha: Export & Data
### 1.0.0-beta: Logic/Protocol Decoding, Themes, Polish
### 1.0.0-rc: Bug Fixes, Documentation
### 1.0.0: Release

### Phase 5: Probe & Calibration
- Probe type selection (1:1, 1:10)
- Probe compensation adjustment
- Self-calibration trigger (if supported)
- Vertical scale auto-adjustment per probe setting

### Phase 6: Polish & Export
- Screenshot/waveform export (CSV, PNG)
- Settings persistence
- Dark/light theme
- Performance optimization

---

## File Structure (Planned)

```
Agilent-U2702A/
+-- .claude/
|   +-- commands/
|       +-- commitversion.md       (custom /commitversion command)
+-- src/
|   +-- main.py                    (app entry point)
|   +-- gui/                       (LAYER 3: GUI -- hardware-independent)
|   |   +-- main_window.py        (main scope window)
|   |   +-- waveform_widget.py    (pyqtgraph display)
|   |   +-- channel_controls.py   (channel settings panel)
|   |   +-- trigger_controls.py   (trigger settings panel)
|   |   +-- measurement_panel.py  (auto measurements)
|   |   +-- multimeter_widget.py  (digital multimeter display)
|   |   +-- probe_settings.py     (per-probe settings page)
|   |   +-- decoder_widget.py     (protocol decode overlay)
|   |   +-- toolbar.py            (run/stop/single/auto)
|   +-- instrument/                (LAYER 1: Communication -- hardware-specific)
|   |   +-- base.py               (abstract oscilloscope interface)
|   |   +-- u2702a.py             (Agilent U2702A implementation)
|   |   +-- connection.py         (USB/VISA connection manager)
|   |   +-- protocol.py           (SCPI command definitions)
|   +-- processing/                (LAYER 2: Analysis -- hardware-independent)
|   |   +-- measurements.py       (Vpp, RMS, freq, etc.)
|   |   +-- fft.py                (FFT analysis)
|   |   +-- probe.py              (probe compensation math)
|   |   +-- decoder.py            (protocol decoding: UART, SPI, I2C)
|   +-- utils/
|       +-- config.py             (settings persistence)
|       +-- session.py            (save/load session files)
|       +-- export.py             (CSV/PNG/NumPy export)
+-- tests/
|   +-- test_measurements.py
|   +-- test_protocol.py
|   +-- test_decoder.py
+-- sessions/                      (user session files, gitignored)
+-- RESEARCH_FINDINGS.md
+-- PROJECT_KNOWLEDGE.md           (this file)
+-- LEARNINGS.md
+-- ARCHITECTURE.md
+-- VERSIONING.md
+-- SCPI_COMMANDS.md
+-- REVERSE_ENGINEERING_GUIDE.md
+-- TODO.md
+-- VERSION                        (current version: 0.1.0-alpha)
+-- requirements.txt
+-- README.md
+-- .gitignore
```

### Layer Separation Rules
1. **`src/instrument/`** -- ONLY hardware communication code lives here. Other users add their scope by creating a new file implementing `base.py`.
2. **`src/processing/`** -- ONLY operates on NumPy arrays. NEVER imports from `instrument/`. No hardware knowledge.
3. **`src/gui/`** -- Uses the abstract interface from `instrument/base.py`. NEVER imports `u2702a.py` directly.

---

## Dependencies

```
pyside6>=6.5
pyqtgraph>=0.13
pyvisa>=1.13
pyvisa-py>=0.7
pyusb>=1.2
numpy>=1.24
scipy>=1.10
libusb (via brew install libusb)
```

---

## Known Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Device needs Windows jump-start | Blocks macOS-only workflow | VM bridge for init, or reverse-engineer init sequence |
| SCPI commands incomplete/undiscoverable | Can't implement all features | Fall back to IVI-COM via VM bridge |
| USB pipe errors on macOS | Connection unreliable | Try different libusb versions, USB reset sequences |
| 8-bit resolution limits measurement accuracy | Measurement precision limited | Document limitations, apply averaging |
| Device discontinued | No future firmware updates | Acceptable -- hardware works fine |

---

## Contacts & Resources

- Keysight Community SCPI thread: https://community.keysight.com/thread/7220
- python-usbtmc U2702A issue: https://github.com/python-ivi/python-usbtmc/issues/31
- Keysight support page: https://www.keysight.com/us/en/support/U2702A/
