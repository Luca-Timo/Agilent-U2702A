# Changelog

All notable changes are listed here, grouped by release. Dates are in
ISO format. Unreleased work that's already landed on ``main`` goes
under "Unreleased"; entries move to a numbered release when the tag
is pushed.

## 1.0.0-beta — 2026-04-18

First feature-complete release. Everything needed to call the project
1.0 from a feature standpoint is in; remaining 1.0.0 work is release-
candidate polish (real-hardware testing pass, any bugs that shake out,
macOS code-signing) rather than new features.

### Added

- **Light theme option.** Settings → Controls → Appearance picks
  Dark (default) or Light. Chrome palette swaps; waveform plot
  canvas stays dark in both for channel-colour readability.
  Restart-on-change; persisted via QSettings.
- **Keyboard Shortcuts dialog.** Help → Keyboard Shortcuts (Ctrl+/ or
  F1 from any window). Three-column reference sheet grouped by
  window context. Single source of truth for the app's bindings.
- **In-app User Guide.** Help → User Guide. Offline usage notes
  covering every major feature (scope, func-gen, sessions, export,
  headless scripting, settings, troubleshooting). Links to the repo's
  detailed docs open in the system browser.
- **Pulse-width (glitch) trigger.** Trigger panel gains a Mode
  selector (Edge / Pulse Width). Pulse Width mode reveals a sub-group
  with polarity, qualifier (greater-than / less-than / within-range /
  outside-range), and threshold knob (10 ns – 10 s). Protocol
  setters added for the previously query-only glitch commands;
  driver exposes six new setting keys under ``trigger.pulse.*``.
- **FFT hover readout.** Mouse over the FFT pane shows a dashed
  orange crosshair locked to the nearest FFT bin, with a label
  showing frequency (SI-formatted) and magnitude (dBV or linear).
- **FFT pane in combined view.** Previously FFT was split-view only;
  now a container-level FFT pane lives below the waveform area in
  both views, with a user-draggable splitter.
- **CHANGELOG.md** (this file). Sync with VERSIONING.md.

### Changed

- **App renamed LabBench → LTB / LabTestBench.** Binary is ``LTB`` /
  ``LTB.app`` / ``LTB.exe`` (short CLI-friendly); display name
  ``LabTestBench`` in window titles and Info.plist. Bundle identifier
  ``com.labtestbench.app``.
- **VERSIONING.md rewritten** to reflect the actual shipped state
  (was three minor versions stale). 0.9.x architecture refactor,
  0.10.x lab-bench architecture, and 0.11.x 33120A support are now
  documented.

### Fixed

- **FFT trace showing as dots, not a line** (introduced in 0.11.0 when
  the FFT pane moved to the container level). Root cause: raw
  ``QtGui.QPen`` is non-cosmetic; pyqtgraph interpreted ``width=1``
  as 1 Hz × 1 dB. Fixed by using ``pg.mkPen(..., width=1.2)``
  consistent with every other trace in the codebase.
- **Launcher teardown crash** when child windows emitted ``destroyed``
  after the launcher's own QLabel had already been deleted during
  app shutdown. Now silently caught.

### Explicitly descoped (per user request)

- Protocol decoding (UART / SPI / I²C / overlay)
- Logic-level view (requires MSO hardware; wait for Rigol MSO2302A)

## 0.11.0-alpha — 2026-04-17

### Added

- **Agilent 33120A function generator support.** Full driver
  implementing ``InstrumentDriver`` with SCPI (FREQ / VOLT /
  VOLT:OFFS / FUNC:SHAP / OUTP / PHAS / OUTP:LOAD / PULS:DCYC).
  Synchronous + thread-safe; runs headless via ``LabSession``.
  ``OUTP OFF`` enforced on every ``open()`` for safety — scripts
  and GUI get the same guarantee.
- **DemoFuncGenBridge** for hardware-free testing; ``GENERIC_DMM``
  and ``AGILENT_33120A`` live in the registry.
- **FunctionGeneratorLayout** with: frequency panel (big knob + SI
  presets), amplitude/offset/load panel, waveform-shape panel
  (6-way grid + duty cycle), big red OUTPUT button, live analytical
  waveform preview.
- **Launcher spawns the right window class** based on
  ``isinstance(cfg, FunctionGeneratorConfig)``; ``InstrumentWindow``
  routes ``GeneratorState`` into every matching widget.
- **Three-instrument session test** (scope + DMM + func-gen in one
  ``LabSession``).
- **LTB / LabTestBench rename** (see 1.0.0-beta Changed section).

## 0.10.0-alpha — Lab-bench architecture

Turned the single-scope app into a multi-instrument bench:

- ``Capabilities`` / ``AcquisitionModel`` enums; ``InstrumentDriver``
  Protocol formalising the driver interface.
- ``U2702ADriver`` extracted from the Qt worker — scope is now
  scriptable headless.
- Config hierarchy (``InstrumentConfig`` → ``OscilloscopeConfig`` /
  ``DMMConfig`` / ``FunctionGeneratorConfig``) and instrument
  registry.
- Layout factories (``OscilloscopeLayout``, ``DMMLayout``).
- ``AcquisitionResult`` hierarchy (``WaveformData`` /
  ``MeterReading`` / ``GeneratorState``).
- ``automation`` package: ``LabSession`` + ``ActionRecorder``.
- Generic-DMM driver.
- ``LauncherWindow`` + ``InstrumentWindow``; multi-window mode.
- ``*IDN?`` auto-discovery (toggleable in Settings).
- PyInstaller build script + GitHub Actions CI (macOS arm64,
  Windows x64, Linux x64).
- 63-test contract suite (``tests/test_driver_headless.py``,
  ``tests/test_automation.py``, ``tests/test_discovery.py``).

## 0.9.0-alpha — Architecture refactor

- **Config centralization.** All scope-specific constants moved to
  ``config/scope_config.py`` as a single source of truth. Adding a
  new oscilloscope means editing one file.
- **Thread safety.** ``QMutex`` + snapshot-per-frame in the
  acquisition worker; session flags / channel settings / trigger
  state all guarded.
- **Session version migration.** ``SESSION_VERSION = "0.9.0"``;
  migrator chain for 0.8.x → 0.9.0 (schema-identical, infra in
  place for future bumps).
- **Performance.** Measurement cache on ``WaveformData`` (skip
  double-compute when toggling cursors / measurements). Hot-path
  array allocations removed.
- **Logging.** Rotating file handler at
  ``~/.config/U2702A/oscilloscope.log``.
- **Safer serial.** Per-call error handling in
  ``_acquire_all_channels``; defensive close on worker shutdown.

## Earlier versions

See ``VERSIONING.md`` for the full 0.1 → 0.8 changelog. Headlines:

- **0.8.x** — export (CSV / JSON / NPZ / PNG / PDF), multi-graph,
  FFT, math (±×÷), reference waveforms, averaging
- **0.7.x** — session save/load, auto-restore, Recent Sessions
- **0.6.x** — DMM mode (DC / AC / AC+DC), min/max/avg, Hold, Rel,
  current via shunt
- **0.5.x** — probe system (1×/10×/100×/1000×/custom)
- **0.4.x** — measurements, cursors
- **0.3.x** — trigger system (edge, slope, sweep, coupling)
- **0.2.x** — Keysight-style UI, knob widget, per-channel controls
- **0.1.x** — USB via ESP32-S3 bridge, SCPI over serial
