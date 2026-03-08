# Version Plan & Feature Staging

> Version format: `major.minor.bugfix-stage`
> Stages: alpha -> beta -> rc (pre-release) -> release
> Current version: 0.1.0-alpha
> Last updated: 2026-03-04

---

## Stage Definitions

| Stage | Meaning | Stability |
|---|---|---|
| `alpha` | Core features in development, expect breaking changes | Unstable |
| `beta` | Feature-complete for the stage, testing & polish | Mostly stable |
| `rc` | Release candidate, bug fixes only | Stable |
| (no suffix) | Production release | Stable |

---

## 0.1.x-alpha -- Foundation & Connection

**Goal**: Establish USB communication with U2702A and display waveforms.

- [ ] Project scaffolding (PySide6 app skeleton)
- [ ] Hardware abstraction layer (separate communication from analysis)
- [ ] USB connection to U2702A via pyvisa-py
- [ ] SCPI command protocol layer (from sniffed commands)
- [ ] Basic 2-channel waveform display (PyQtGraph)
- [ ] Run / Stop / Single acquisition
- [ ] Status bar (connection state, sample rate)

**Milestone**: Can connect to scope and see live waveforms on screen.

---

## 0.2.x-alpha -- Controls & Scaling

**Goal**: Full oscilloscope control panel.

- [ ] Vertical scale (V/div) per channel
- [ ] Horizontal scale (T/div)
- [ ] Channel enable/disable
- [ ] Channel coupling (AC/DC)
- [ ] Vertical offset per channel
- [ ] Horizontal position/offset
- [ ] Graticule overlay (scope grid)

**Milestone**: Can adjust all basic scope settings from the GUI.

---

## 0.3.x-alpha -- Trigger System

**Goal**: Functional trigger system.

- [ ] Edge trigger (rising/falling)
- [ ] Trigger source selection (CH1/CH2)
- [ ] Trigger level adjustment
- [ ] Trigger mode: Auto / Normal / Single
- [ ] Trigger status indicator
- [ ] Pulse width trigger

**Milestone**: Stable triggered acquisitions.

---

## 0.4.x-alpha -- Measurements & Math

**Goal**: Automatic measurements and signal analysis.

- [ ] Vpp, Vmax, Vmin measurements
- [ ] Vrms (AC and DC) measurements
- [ ] Frequency and period measurements
- [ ] Rise/fall time measurements
- [ ] Duty cycle measurement
- [ ] Measurement display panel
- [ ] Cursor measurements (time + voltage)

**Milestone**: All standard oscilloscope measurements working.

---

## 0.5.x-alpha -- Probe & Calibration

**Goal**: Probe configuration and calibration.

- [ ] Probe settings page (per-probe configuration)
- [ ] Probe type selection: 1:1, 1:10
- [ ] Probe factor applied to all measurements and display
- [ ] Probe compensation check
- [ ] Self-calibration trigger (if device supports it)
- [ ] Custom probe attenuation factor (user-defined)

**Milestone**: Accurate measurements with any probe type.

---

## 0.6.x-alpha -- Multimeter Mode

**Goal**: Digital multimeter display mode.

- [ ] Multimeter mode toggle (per channel or both)
- [ ] Large digital voltage display (DC, AC RMS, AC+DC RMS)
- [ ] Frequency counter display
- [ ] Min/Max/Average tracking
- [ ] Auto-range display
- [ ] Switchable between scope view and multimeter view

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
