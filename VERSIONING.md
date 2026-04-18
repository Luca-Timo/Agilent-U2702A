# Version Plan & Feature Staging

> Version format: `major.minor.bugfix-stage`
> Stages: alpha -> beta -> rc (pre-release) -> release
> Current version: 1.0.0-beta
> Last updated: 2026-04-18

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

USB communication via ESP32-S3 bridge, SCPI protocol layer, serial bridge client, SCPI Tester, status bar.

## 0.2.x-alpha -- Controls, Scaling & Trigger ✅

Keysight-style front panel, custom knobs, V/div / T/div, channel enable + coupling, trigger controls, measurements, dark theme, settings dialog, GPL v3 license.

## 0.3.x-alpha -- Trigger System ✅

Edge trigger with source/slope/sweep/coupling, trigger mode (Auto/Normal/Single), trigger status indicator, crossing marker, slope arrow, software trigger alignment, drag-to-zoom + Cmd+Z undo.

- [x] Pulse-width trigger (GUI wired in 1.0.0-beta; protocol was already defined)

## 0.4.x-alpha -- Measurements & Math ✅

Vpp / Vmax / Vmin / Vrms / frequency / period / rise / fall / duty; toggleable measurement panel; cursor system with readout bar.

## 0.5.x-alpha -- Probe & Calibration ✅

1:1 / 1:10 / 1:100 / 1:1000 / custom probe factors; probe compensation dialog; effective V/div label; probe badges on GND markers.

## 0.6.x-alpha -- Multimeter Mode ✅

DC / AC RMS / AC+DC RMS display, Min/Max/Avg tracking, auto-range, current mode via shunt, Hold / Relative / Range-Lock.

## 0.7.x-alpha -- Session Files & Persistence ✅

JSON session save/load, Recent Sessions, auto-save + auto-restore, QSettings (geometry, last port/baud).

## 0.8.x-alpha -- Export, Data & Multi-Graph ✅

Waveform export (CSV / JSON / NPZ), import waveform data, graph export (PNG / PDF, dark & light), unified Export dialog, multi-graph / split view, FFT, math (CH1+CH2, CH1-CH2, CH1×CH2, CH1÷CH2), reference waveform storage/recall, waveform averaging, knob-scroll-off default.

## 0.9.0-alpha -- Architecture Refactor ✅

Config centralization (`config/scope_config.py` as single source of truth for scope-specific values), thread safety in acquisition worker (QMutex + snapshot-per-frame), session version migration, structured logging, per-call serial error handling, performance fixes (measurement cache, hot-path allocation removal), small cleanups (DMM autorange modulo, AppSettings singleton, bulk cursor setters).

## 0.10.0-alpha -- Lab Bench Architecture ✅

Turned the single-scope app into a multi-instrument "lab bench":

- `Capabilities` + `InstrumentDriver` Protocol
- Extract `U2702ADriver` from the Qt worker (fully headless-scriptable)
- Config hierarchy (`InstrumentConfig` → `OscilloscopeConfig` / `DMMConfig` / `FunctionGeneratorConfig`)
- `LayoutFactory` (`OscilloscopeLayout`, `DMMLayout`, `FunctionGeneratorLayout`)
- `AcquisitionResult` hierarchy (`WaveformData` / `MeterReading` / `GeneratorState`)
- `automation` package (`LabSession`, `ActionRecorder`)
- `*IDN?` auto-discovery (toggleable in Settings)
- Generic-DMM driver (SCPI-standard)
- `LauncherWindow` + `InstrumentWindow`, multi-window mode
- PyInstaller build + GitHub Actions CI (macOS arm64 / Windows x64 / Linux x64)

## 0.11.0-alpha -- Agilent 33120A + LTB rename ✅

- `Agilent33120ADriver` (RS-232 via USB-RS232 adapter, output-off safety invariant)
- `DemoFuncGenBridge`, `FunctionGeneratorLayout` (preview + output indicator + control panels)
- Launcher branch + `InstrumentWindow` `GeneratorState` routing
- App renamed `LabBench` → `LTB` (binary) / `LabTestBench` (display)
- FFT pane in combined view (not only split) + live hover readout

---

## 1.0.0-beta -- Feature Complete ✅ (2026-04-18)

All planned 1.0.0 features integrated.

- [x] Light theme option (dark remains default; export already supports both)
- [x] Keyboard-shortcut audit + in-app Shortcuts dialog (Ctrl+/ or F1)
- [x] In-app user documentation (Help → User Guide)
- [x] Pulse-width trigger GUI (open since 0.3.x)
- [x] Launcher teardown `destroyed`-signal crash fix
- [x] Performance target (30+ FPS continuous) — already met
- [x] CHANGELOG.md

## 1.0.0-rc -- Pre-Release

- [ ] All known bugs fixed
- [ ] Community testing feedback addressed
- [ ] Edge-case handling pass
- [x] Installation guide (macOS / Windows / Linux — in README)
- [x] Performance profiling

## 1.0.0 -- Release

- [ ] Final testing pass against real U2702A + 33120A
- [ ] CHANGELOG / release notes
- [x] Standalone bundle (macOS .app / Windows .exe / Linux tarball) — in CI
- [ ] Developer-ID signing + notarization (macOS; optional, ~$99/yr)

---

## Post-1.0 / Future (not blocking 1.0.0)

### Explicitly descoped per user request (no ship date)

- Protocol decoding: UART / SPI / I²C / overlay — **skipped**
- Logic-level view — **skipped** (needs MSO hardware anyway)

### Future instruments (queued — see `project_future_instruments.md`)

- [ ] Rigol MSO2302A — 2ch analog + 16ch logic; first LAN/TCP transport; first mixed-signal scope (`TCPBridge` class)
- [ ] Racal-Dana 1992 — universal counter/timer; first `InstrumentKind.COUNTER`; likely pre-SCPI dialect; possibly first `GPIBBridge`
- [ ] Full Agilent 33120A feature set — AM/FM/FSK modulation, sweep (linear/log), burst, arbitrary-waveform upload

### Nice-to-have

- [ ] **Per-instrument + multi-instrument session files** — today `gui/session.py` saves a single scope's state. Extend to save/load one instrument at a time (from its own window) AND the full bench (from the launcher). Move the "how to serialize" responsibility onto each driver (`gather_state` / `apply_state`) so adding a new instrument kind automatically gets session support. ~8-10 hours. (Backlogged 2026-04-18.)
- [ ] Automated probe compensation (drive 33120A + measure overshoot/settling)
- [ ] External trigger input support
- [ ] TV trigger mode
- [ ] XY display mode
- [ ] Persistence display (intensity-graded)
- [ ] Segmented memory acquisition
- [ ] Additional protocol decoders (CAN, LIN, 1-Wire) — iff decoding gets un-descoped
- [x] Plugin system for community hardware drivers — effectively achieved via the lab-bench architecture
- [ ] Mask testing
- [ ] Power analysis measurements
- [ ] JSON-RPC IPC server so external processes can drive a running GUI (`automation/ipc.py`)

---

## Modular Architecture (fulfilled by the lab-bench refactor)

As of 0.10.0-alpha the three layers are formal:

```
config/                         # hardware profiles per model
    instrument_config.py        # InstrumentConfig + kind-specific subclasses
    presets/                    # per-model presets (u2702a, generic_dmm, 33120a, …)

instrument/                     # transport + drivers
    serial_bridge.py            # pyserial Bridge
    demo_bridge.py + variants   # synthetic bridges for demo mode
    capabilities.py             # InstrumentKind, AcquisitionModel, Capabilities
    driver.py                   # InstrumentDriver Protocol
    discovery.py                # *IDN? probing
    drivers/                    # per-model drivers (u2702a, generic_dmm, agilent_33120a, …)

processing/                     # hardware-independent analysis
    acquisition_result.py       # WaveformData / MeterReading / GeneratorState
    measurements.py, fft.py, averaging.py, math_ops.py, …

automation/                     # headless scripting
    session.py                  # LabSession
    recorder.py                 # ActionRecorder (save/load/replay)

gui/                            # hardware-independent display
    launcher_window.py          # top-level
    instrument_window.py        # generic per-instrument shell
    main_window.py              # scope-specialised window
    layouts/                    # per-kind LayoutFactory
```

Adding a new instrument = preset + driver + optional layout, registered in `config/__init__.py` and `automation/session.py`. Three consumers so far (U2702A, Generic-DMM, 33120A) confirm the seams.
