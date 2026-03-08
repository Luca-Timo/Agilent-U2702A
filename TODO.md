# Project TODO

> Master task tracker for the U2702A macOS Oscilloscope project.
> Check off items as they are completed.
> Last updated: 2026-03-06

---

## Phase 0: Protocol Discovery (IN PROGRESS)

- [x] Set up Windows machine with USB connection
- [x] Install Agilent IO Library Suite + AMM on Windows
- [x] Connect U2702A and verify device detected (VID=0x0957, PID=0x2918)
- [x] Capture USB traffic via Wireshark/USBPcap (`USB_dump_ch1_2_single.pcapng`)
- [x] Extract SCPI commands from capture (`parse_usb_capture.py` — 12,004 exchanges, 52 unique commands)
- [x] Document captured commands in SCPI_COMMANDS.md
- [x] Determine waveform data binary format (IEEE 488.2, 8-bit unsigned, 2512 samples/transfer)
- [x] **Capture 2: all AMM functions** (`USB_dump_2_all_funct.pcapng` — 31,502 exchanges, 61 commands)
  - [x] `*IDN?` — `AGILENT TECHNOLOGIES,U2702A,MY50032044,V2.47-2.05-1.05`
  - [x] AC coupling (`CHANNEL:COUPLING AC`), BW limit (`BWLIMIT ON/OFF`)
  - [x] V/div: 2mV–5V confirmed, T/div: 1ns–1us captured + GUI range documented
  - [x] Trigger: all types (EDGE/GLIT/TV), slopes, coupling, sources
  - [x] WAV:PREAMBLE — confirmed AMM never uses it (likely doesn't exist)
  - [x] WAV:SOURCE — confirmed AMM never uses it (likely doesn't exist)
  - [x] Probe attenuation — confirmed DOES NOT EXIST via Interactive IO
- [x] **Tested remaining commands via Interactive IO** (all timeout = don't exist):
  - [x] `WAV:PREAMBLE?`, `WAV:PRE?` — DOES NOT EXIST
  - [x] `WAV:SOURCE`, `WAV:SOUR?` — query DOES NOT EXIST, but `WAV:SOUR CHAN1`/`CHAN2` (set) WORKS
  - [x] `MEAS:VPP?` — DOES NOT EXIST
  - [x] `CHANNEL1:PROBE?` — DOES NOT EXIST
  - [x] `*RST` — DOES NOT EXIST
- [x] Confirmed `WAV:SOUR CHAN1`/`CHAN2` accepted + data structure: 2 prefix + 1256 data + 1256 zeros
- [x] Documented firmware boot requirement (PID 0x2818 -> 0x2918)
- [ ] Attempt connection from macOS via pyvisa-py — `python test_connection.py`
- [ ] **Investigate WAV:SOUR channel switching** — disconnect probe from one channel, confirm `WAV:SOUR CHAN1` vs `CHAN2` returns different data (after macOS connection + init working)

## Phase 1: macOS Connection (IN PROGRESS)

- [x] Install dependencies on macOS (`brew install libusb` + venv with pyvisa/pyusb/numpy/scipy)
- [x] Write USB boot module (`instrument/boot.py`) — PID 0x2818 -> 0x2918 firmware init
- [x] Write connection manager (`instrument/connection.py`) — auto-detect, boot, VISA session
- [x] Write SCPI protocol definitions (`instrument/protocol.py`) — all captured commands
- [x] Write test script (`test_connection.py`) — scan, connect, init, single acquisition
- [ ] **Test with actual hardware** — plug in U2702A and run `python test_connection.py -v`
- [ ] Implement connection retry/recovery logic

## Phase 2: Core GUI Shell

- [ ] Create PySide6 main window with scope-like layout
- [ ] Implement PyQtGraph waveform display widget
- [ ] Add graticule overlay (grid lines like real scope)
- [ ] Create toolbar: Run, Stop, Single, Auto
- [ ] Create channel control panels (CH1, CH2)
- [ ] Create timebase control panel
- [ ] Create trigger control panel
- [ ] Create measurement display panel
- [ ] Add status bar (connection, sample rate, memory depth)

## Phase 3: Waveform Acquisition

- [ ] Implement acquisition thread (QThread)
- [ ] Continuous acquisition loop with Run/Stop
- [ ] Single acquisition mode
- [ ] Waveform data parsing (raw -> voltage)
- [ ] Connect acquisition thread to waveform display
- [ ] Vertical scale (V/div) control wired to device
- [ ] Horizontal scale (T/div) control wired to device
- [ ] Channel enable/disable

## Phase 4: Trigger System

- [ ] Edge trigger implementation (rising/falling)
- [ ] Trigger source selection (CH1/CH2)
- [ ] Trigger level adjustment
- [ ] Trigger mode: Auto / Normal
- [ ] Trigger status indicator in GUI
- [ ] Pulse width trigger (if supported)

## Phase 5: Measurements

- [ ] Vpp measurement
- [ ] Vrms measurement (DC)
- [ ] Vrms measurement (AC)
- [ ] Frequency measurement
- [ ] Period measurement
- [ ] Rise time measurement
- [ ] Fall time measurement
- [ ] Duty cycle measurement
- [ ] Cursor measurements (voltage + time)
- [ ] Measurement display in panel

## Phase 6: Probe & Calibration

- [ ] Probe selection UI (1:1, 1:10)
- [ ] Probe factor applied to all measurements and display
- [ ] Probe compensation check (if device supports cal output)
- [ ] Self-calibration trigger
- [ ] Vertical scale labels adjusted for probe setting

## Phase 7: Polish & Export

- [ ] CSV waveform export
- [ ] PNG screenshot export
- [ ] Settings persistence (QSettings)
- [ ] Dark theme (default) + light theme option
- [ ] FFT math function
- [ ] Waveform averaging
- [ ] About dialog
- [ ] Error handling and user-friendly error messages
- [ ] Performance optimization (target: 30+ FPS continuous acquisition)

## Stretch Goals

- [ ] XY display mode
- [ ] Persistence display (intensity graded)
- [ ] Reference waveform storage/recall
- [ ] TV trigger
- [ ] Segmented memory acquisition
- [ ] LAN bridge mode (access scope over network)
- [ ] pyinstaller/cx_Freeze packaging for standalone .app
