# Version Plan & Feature Staging

> Version format: `major.minor.bugfix-stage`
> Stages: alpha -> beta -> rc (pre-release) -> release
> Current version: 0.6.0-alpha
> Last updated: 2026-03-13

---

## Stage Definitions

| Stage | Meaning | Stability |
|---|---|---|
| `alpha` | Core features in development, expect breaking changes | Unstable |
| `beta` | Feature-complete for the stage, testing & polish | Mostly stable |
| `rc` | Release candidate, bug fixes only | Stable |
| (no suffix) | Production release | Stable |

---

## 0.1.x-alpha -- Foundation & Connection ✅

**Goal**: Establish USB communication with U2702A and display waveforms.

- [x] Project scaffolding (PySide6 app skeleton)
- [x] Hardware abstraction layer (separate communication from analysis)
- [x] USB connection via ESP32-S3 bridge (replaced pyvisa-py)
- [x] SCPI command protocol layer (from sniffed commands)
- [x] SCPI Tester GUI (send/receive commands, binary waveform display)
- [x] Serial bridge client (thread-safe, binary protocol)
- [x] Status bar (connection state)

**Milestone**: Full SCPI round-trip working — text ~1ms, binary waveforms ~39ms.

---

## 0.2.x-alpha -- Controls, Scaling & Trigger ✅

**Goal**: Full oscilloscope GUI with controls, scaling, trigger, and measurements.

- [x] Keysight-style front panel layout (graph left, controls right)
- [x] Custom rotary knob widget (drag-to-turn + click-to-edit popup)
- [x] Vertical scale (V/div) per channel via knob
- [x] Horizontal scale (T/div) via knob
- [x] Channel enable/disable (N-channel scalable architecture)
- [x] Channel coupling (AC/DC) dropdown
- [x] Vertical offset per channel via knob
- [x] Horizontal position via knob
- [x] Graticule overlay (scope grid)
- [x] Edge trigger controls (level knob, source, slope, sweep, coupling)
- [x] Basic measurements (Vpp, Vmin, Vmax, frequency, period)
- [x] Connection dialog (separate window)
- [x] Settings dialog (channel colors, probe attenuation)
- [x] SCPI Tester accessible from Tools menu (shared connection)
- [x] Dark theme (Fusion style)
- [x] Measurement toggle buttons (Vpp, Vmin, Vmax, Vrms, Vmean, Freq, Period)
- [x] Per-channel GND/0V markers on Y-axis (arrow + channel number)
- [x] Trigger position marker on X-axis (▼ triangle)
- [x] Larger default window size (1440×900)
- [x] Trigger level indicator (dashed line + right-edge badge)
- [x] Software trigger alignment (trigger edge at center marker)
- [x] GPL v3 license
- [x] About/License dialog in Help menu

**Milestone**: Can control all scope settings from the GUI and see live waveforms.

---

## 0.3.x-alpha -- Trigger System ✅

**Goal**: Functional trigger system.

- [x] Edge trigger (rising/falling/either/alternating)
- [x] Trigger source selection (CH1/CH2/EXT)
- [x] Trigger level adjustment (knob + drag on graph)
- [x] Trigger mode: Auto / Normal / Single
- [x] Trigger status indicator (ARMED/TRIG'D/AUTO/READY)
- [x] Trigger crossing marker on waveform trace (interpolated position)
- [x] Trigger slope indicator (dropdown + crossing label ↗/↘/↕/⇅)
- [x] Trigger coupling (DC/AC/LFR/HFR)
- [x] Software trigger alignment (crossing detection)
- [x] Drag-to-zoom with Cmd+Z undo
- [ ] Pulse width trigger (protocol defined, GUI not yet wired)

**Milestone**: Stable triggered acquisitions.

---

## 0.4.x-alpha -- Measurements & Math ✅

**Goal**: Automatic measurements and signal analysis.

- [x] Vpp, Vmax, Vmin measurements
- [x] Vrms (AC and DC) measurements
- [x] Frequency and period measurements
- [x] Measurement display panel (toggle buttons + per-channel grid)
- [x] Rise/fall time measurements (10%/90% threshold interpolation)
- [x] Duty cycle measurement (midpoint threshold)
- [x] Cursor measurements (time + voltage, draggable lines + readout bar)
- [x] Cursor readout panel (ΔT, 1/ΔT, ΔV)
- [x] Toolbar cleanup (consistent button/indicator sizing)
- [x] Settings: knob scroll wheel toggle

**Milestone**: All standard oscilloscope measurements working.

---

## 0.5.x-alpha -- Probe & Calibration ✅

**Goal**: Probe configuration and calibration.

- [x] Probe settings page (per-probe configuration)
- [x] Probe type selection: 1:1, 1:10, 1:100, 1:1000
- [x] Probe factor applied to all measurements and display
- [x] Probe compensation check (guidance dialog)
- [x] Self-calibration trigger (N/A — U2702A has no CAL SCPI commands)
- [x] Custom probe attenuation factor (user-defined via dialog)
- [x] Effective V/div label (shown when probe ≠ 1x)
- [x] Probe badge on waveform GND markers

**Milestone**: Accurate measurements with any probe type.

---

## 0.6.x-alpha -- Multimeter Mode ← CURRENT

**Goal**: Digital multimeter display mode.

- [x] Multimeter mode toggle (utility panel button, disables scope-only controls)
- [x] Large digital voltage display (DC, AC RMS, AC+DC RMS)
- [x] Frequency counter display
- [x] Min/Max/Average tracking (per-channel, reset button)
- [x] Auto-range display (throttled V/div adjustment in DMM mode)
- [x] Switchable between scope view and multimeter view (widget swap)

**Milestone**: Can use scope as a basic digital multimeter.

---

## 0.7.x-alpha -- Session Files & Persistence

**Goal**: Save/load workspace configurations.

- [ ] Session file format (JSON or YAML)
- [ ] Save current setup: channel config, timebase, trigger, probe, display settings
- [ ] Load session file and restore all settings
- [ ] File > Open / Save / Save As dialogs
- [ ] Recent files list
- [ ] Auto-save last session on exit, restore on start
- [ ] Settings persistence via QSettings (window position, preferences)

**Milestone**: Users can save and recall their scope setups.

---

## 0.8.x-alpha -- Export & Data

**Goal**: Data export capabilities.

- [ ] Waveform export to CSV
- [ ] Waveform export to NumPy (.npy)
- [ ] Screenshot export (PNG)
- [ ] FFT math function display
- [ ] Waveform averaging
- [ ] Reference waveform storage/recall

**Milestone**: Can export data for analysis in other tools.

---

## 1.0.0-beta -- Feature Complete

**Goal**: All planned features integrated, testing phase.

- [ ] Logic level view (configurable threshold)
- [ ] Protocol decoding: UART
- [ ] Protocol decoding: SPI
- [ ] Protocol decoding: I2C
- [ ] Protocol decode overlay on waveform
- [ ] Dark theme (default)
- [ ] Light theme option
- [ ] About dialog
- [ ] Keyboard shortcuts
- [ ] Error handling and user-friendly messages
- [ ] Performance optimization (target: 30+ FPS continuous)

**Milestone**: All features working, enter testing phase.

---

## 1.0.0-rc -- Pre-Release

**Goal**: Bug fixes, polish, documentation.

- [ ] All known bugs fixed
- [ ] User documentation / help
- [ ] Installation guide (macOS)
- [ ] Performance profiling and optimization
- [ ] Edge case handling
- [ ] Community testing feedback addressed

**Milestone**: Ready for public release.

---

## 1.0.0 -- Release

**Goal**: Stable public release.

- [ ] Final testing pass
- [ ] README with full documentation
- [ ] pyinstaller / cx_Freeze standalone .app bundle
- [ ] Release notes

---

## Nice to Have (Post 1.0 / Future)

- [ ] External trigger input support
- [ ] TV trigger mode
- [ ] XY display mode
- [ ] Persistence display (intensity graded)
- [ ] Segmented memory acquisition
- [ ] LAN bridge mode (access scope over network)
- [ ] Additional protocol decoders (CAN, LIN, 1-Wire, etc.)
- [ ] Plugin system for community hardware drivers
- [ ] Waveform math (CH1+CH2, CH1-CH2, CH1*CH2)
- [ ] Mask testing
- [ ] Power analysis measurements

---

## Modular Architecture Requirement

The codebase MUST separate:

1. **Communication Layer** (`src/instrument/`) -- hardware-specific USB/SCPI communication
   - Abstract base class for any oscilloscope
   - U2702A-specific implementation
   - Other users can add their own hardware by implementing the base class

2. **Analysis Layer** (`src/processing/`) -- hardware-independent signal analysis
   - Measurements, FFT, protocol decoding, math
   - Works on NumPy arrays regardless of source hardware

3. **GUI Layer** (`src/gui/`) -- hardware-independent display
   - Waveform display, controls, panels
   - Binds to the abstract instrument interface, not U2702A directly

```
src/instrument/
    base.py             # Abstract oscilloscope interface
    u2702a.py           # Agilent U2702A implementation
    # future: rigol_ds1054z.py, siglent_sds1104.py, etc.

src/processing/
    measurements.py     # Vpp, RMS, freq -- works on any waveform data
    fft.py              # FFT analysis
    probe.py            # Probe compensation math
    decoder.py          # Protocol decoding (UART, SPI, I2C)

src/gui/
    main_window.py      # Uses abstract instrument interface
    waveform_widget.py  # Displays NumPy arrays, doesn't know about hardware
    ...
```

This way, anyone can add support for their own oscilloscope by implementing `base.py`.
