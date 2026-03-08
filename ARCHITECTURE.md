# Architecture & Implementation Plan

> Technical architecture for the U2702A macOS oscilloscope GUI.
> Version: 0.1.0-alpha
> Last updated: 2026-03-04
>
> See VERSIONING.md for feature staging (alpha/beta/rc/release).

---

## Design Principle: Modular & Hardware-Agnostic

The codebase is split into three independent layers:
1. **Communication Layer** -- hardware-specific, implements abstract interface
2. **Analysis Layer** -- hardware-independent, operates on NumPy arrays
3. **GUI Layer** -- hardware-independent, binds to abstract instrument interface

This allows other users to add support for their own oscilloscope hardware
by implementing the abstract base class -- no changes to analysis or GUI needed.

---

## System Architecture

```
+------------------------------------------------------------------+
|                    PySide6 GUI (Main Thread)                      |
|  +-------------------+  +-------------------+  +---------------+ |
|  | Waveform Display  |  | Channel Controls  |  | Measurements  | |
|  | (PyQtGraph)       |  | (V/div, coupling) |  | (Vpp, RMS...) | |
|  +-------------------+  +-------------------+  +---------------+ |
|  +-------------------+  +-------------------+  +---------------+ |
|  | Trigger Controls  |  | Timebase Controls |  | Toolbar       | |
|  | (edge, level)     |  | (T/div, position) |  | (Run/Stop...) | |
|  +-------------------+  +-------------------+  +---------------+ |
|  +-------------------+  +-------------------+  +---------------+ |
|  | Multimeter Mode   |  | Probe Settings    |  | Protocol      | |
|  | (digital display) |  | (per-probe config)|  | Decoder View  | |
|  +-------------------+  +-------------------+  +---------------+ |
+------------------------------------------------------------------+
           |                        ^
           | Commands               | Waveform Data + Status
           v                        |
+------------------------------------------------------------------+
|               Acquisition Thread (QThread)                        |
|  +-------------------+  +-------------------+                    |
|  | Command Queue     |  | Data Parser       |                    |
|  | (thread-safe)     |  | (raw -> voltage)  |                    |
|  +-------------------+  +-------------------+                    |
+------------------------------------------------------------------+
           |                        ^
           | SCPI Commands          | Raw USB Data
           v                        |
+------------------------------------------------------------------+
|       Abstract Instrument Interface (base.py)                     |
|  +-----------------------------------------------------------+   |
|  | connect() | read_waveform() | configure_channel() | ...   |   |
|  +-----------------------------------------------------------+   |
|       |                                                           |
|  +-------------------+  +-------------------+                    |
|  | U2702A Driver     |  | (Future: other    |                    |
|  | (u2702a.py)       |  |  hardware drivers)|                    |
|  +-------------------+  +-------------------+                    |
+------------------------------------------------------------------+
           |                        ^
           v                        |
+------------------------------------------------------------------+
|               PyVISA + pyvisa-py + PyUSB + libusb                |
+------------------------------------------------------------------+
           |                        ^
           v                        |
+------------------------------------------------------------------+
|               USB Hardware (U2702A @ 0x0957:0x2918)              |
+------------------------------------------------------------------+
```

---

## Threading Model

```
Main Thread (GUI)
    |
    +-- QThread: AcquisitionWorker
    |       - Continuous acquisition loop
    |       - Sends SCPI commands via PyVISA
    |       - Emits waveform data via Qt signals
    |       - Respects Run/Stop state
    |
    +-- QThread: MeasurementWorker (optional)
            - Processes waveform data
            - Calculates Vpp, RMS, frequency, etc.
            - Emits results via Qt signals
```

### Thread Communication
- **GUI -> Acquisition**: `QQueue` or shared state with mutex for commands
- **Acquisition -> GUI**: Qt signals (`pyqtSignal` / PySide6 `Signal`)
- **Data format**: NumPy arrays for waveform data

---

## Key Classes

### `MainWindow` (gui/main_window.py)
- Top-level PySide6 window
- Manages layout: waveform display, controls, measurements
- Handles menu bar, status bar
- Coordinates all child widgets

### `WaveformWidget` (gui/waveform_widget.py)
- Wraps PyQtGraph `PlotWidget`
- Displays 2 channels with independent colors
- Grid overlay (like real oscilloscope graticule)
- Cursor support (horizontal + vertical)
- Auto-scale and manual scale modes

### `U2702A` (instrument/u2702a.py)
- High-level device driver
- Methods: `connect()`, `disconnect()`, `configure_channel()`, `read_waveform()`, `set_trigger()`, etc.
- Abstracts SCPI commands into Pythonic API
- Handles data parsing (raw bytes -> voltage array)

### `SCPIProtocol` (instrument/protocol.py)
- SCPI command string definitions
- Command builder methods
- Response parsers
- **This file will be populated after Phase 0 (SCPI sniffing)**

### `ConnectionManager` (instrument/connection.py)
- PyVISA resource manager wrapper
- Auto-detect U2702A by VID:PID
- Connection retry logic
- USB reset/recovery

### `Measurements` (processing/measurements.py)
- Static methods for all measurement types
- Input: NumPy waveform array + sample rate + probe factor
- Output: measurement value + unit string

```python
class Measurements:
    @staticmethod
    def vpp(data): return np.max(data) - np.min(data)

    @staticmethod
    def vrms(data): return np.sqrt(np.mean(data ** 2))

    @staticmethod
    def vrms_ac(data): return np.sqrt(np.mean((data - np.mean(data)) ** 2))

    @staticmethod
    def frequency(data, sample_rate): ...

    @staticmethod
    def period(data, sample_rate): ...

    @staticmethod
    def rise_time(data, sample_rate): ...

    @staticmethod
    def fall_time(data, sample_rate): ...

    @staticmethod
    def duty_cycle(data, sample_rate): ...
```

### `ProbeConfig` (processing/probe.py)
- Probe attenuation factors: 1:1 (1x), 1:10 (10x)
- Applies scaling to voltage data
- Adjusts vertical scale display
- Probe compensation frequency check

---

## Data Flow: Single Acquisition

```
1. User clicks "Single" button
2. MainWindow sends "single" command to AcquisitionWorker
3. AcquisitionWorker:
   a. Sends trigger config SCPI commands
   b. Sends acquisition start SCPI command
   c. Waits for trigger (polls status or waits)
   d. Sends waveform read SCPI command
   e. Receives raw binary data
   f. Parses: raw bytes -> ADC counts -> voltage values
   g. Applies probe scaling
   h. Emits Signal(channel_id, np.ndarray, metadata)
4. MainWindow receives signal:
   a. Updates WaveformWidget with new data
   b. Triggers MeasurementPanel recalculation
   c. Updates status bar (trigger status, sample rate)
```

---

## Data Flow: Continuous Acquisition

```
1. User clicks "Run" button
2. AcquisitionWorker enters loop:
   while running:
       a. Send acquisition command
       b. Wait for trigger
       c. Read waveform data
       d. Parse and emit signal
       e. Check for stop flag
3. GUI updates on each signal emission
4. User clicks "Stop" -> sets stop flag -> loop exits
```

---

## Waveform Data Format

```python
@dataclass
class WaveformData:
    channel: int              # 1 or 2
    raw_data: np.ndarray      # Raw ADC values (uint8 for 8-bit)
    voltage_data: np.ndarray  # Scaled voltage values (float64)
    sample_rate: float        # Actual sample rate in Sa/s
    time_offset: float        # Time of first sample
    voltage_offset: float     # Vertical offset
    voltage_scale: float      # V/div setting
    time_scale: float         # T/div setting
    probe_factor: float       # 1.0 or 10.0
    num_points: int           # Number of data points
    timestamp: float          # Acquisition timestamp
```

---

## GUI Layout (ASCII Mockup)

```
+--------------------------------------------------------------+
| File  View  Acquire  Measure  Math  Utility  Help            |
+--------------------------------------------------------------+
| [Run] [Stop] [Single] [Auto] | CH1 [ON] CH2 [ON] | [Probe]  |
+--------------------------------------------------------------+
|                                                    |  CH1     |
|                                                    | V/div:   |
|          Waveform Display Area                     | [1V  v]  |
|          (PyQtGraph with graticule)                | Coupling:|
|                                                    | [DC   v] |
|    CH1: ~~~~~~~~~~~~~~~~~~~~                       | Offset:  |
|    CH2:     ~~~~~~~~~~~~~~~~~~~~                   | [0.0V  ] |
|                                                    |----------|
|                                                    |  CH2     |
|                                                    | V/div:   |
|                                                    | [1V  v]  |
|                                                    | Coupling:|
|                                                    | [DC   v] |
+--------------------------------------------------------------+
| T/div: [1ms v] | Trig: [CH1 v] [Edge v] Level: [0.0V]       |
+--------------------------------------------------------------+
| Measurements:                                                 |
| CH1: Vpp=3.3V  Vrms=1.65V  Freq=1.00kHz  Period=1.00ms      |
| CH2: Vpp=5.0V  Vrms=2.50V  Freq=50.0Hz   Period=20.0ms      |
+--------------------------------------------------------------+
| Status: Connected (USB::0x0957::0x2918) | 500 MSa/s | 16Mpts |
+--------------------------------------------------------------+
```

---

## Technology Stack Summary

| Layer | Technology | Version |
|---|---|---|
| GUI Framework | PySide6 | >= 6.5 |
| Waveform Plot | PyQtGraph | >= 0.13 |
| VISA Abstraction | PyVISA | >= 1.13 |
| VISA Backend | pyvisa-py | >= 0.7 |
| USB Access | PyUSB | >= 1.2 |
| Native USB | libusb | via brew |
| Numerics | NumPy | >= 1.24 |
| Signal Processing | SciPy | >= 1.10 |
| Python | CPython | >= 3.10 |
| OS | macOS | Ventura+ |

---

## Feature Checklist

> Full staging details in VERSIONING.md

### Core Scope Features
- [ ] USB connection to U2702A (hardware-agnostic base class)
- [ ] 2-channel waveform display
- [ ] Run / Stop / Single acquisition
- [ ] Vertical scale (V/div) per channel
- [ ] Horizontal scale (T/div)
- [ ] Channel coupling (AC/DC)
- [ ] Edge trigger (channel, level, slope)
- [ ] Pulse width trigger
- [ ] Trigger modes: Auto / Normal / Single
- [ ] Graticule overlay

### Measurements
- [ ] Vpp, Vmax, Vmin
- [ ] Vrms (AC and DC)
- [ ] Frequency, Period
- [ ] Rise/fall time
- [ ] Duty cycle
- [ ] Cursor measurements (time + voltage)

### Probe System
- [ ] Per-probe settings page
- [ ] Probe type selection: 1:1, 1:10, custom
- [ ] Probe compensation check
- [ ] Calibration wizard

### Multimeter Mode
- [ ] Digital voltage display (DC, AC RMS, AC+DC RMS)
- [ ] Frequency counter
- [ ] Min/Max/Average tracking
- [ ] Auto-range
- [ ] Per-channel or dual-channel mode

### Logic & Protocol Decoding
- [ ] Logic level view (configurable threshold)
- [ ] UART decoder
- [ ] SPI decoder
- [ ] I2C decoder
- [ ] Decode overlay on waveform

### Session & Data Management
- [ ] Save/load session files (channel config, timebase, trigger, probe, display)
- [ ] File > Open / Save / Save As
- [ ] Recent files list
- [ ] Auto-save/restore last session
- [ ] Waveform export (CSV, NumPy)
- [ ] Screenshot export (PNG)

### Math & Analysis
- [ ] FFT math function
- [ ] Waveform averaging
- [ ] Reference waveform storage/recall

### Polish
- [ ] Dark/light theme
- [ ] Keyboard shortcuts
- [ ] Error handling & user-friendly messages
- [ ] About dialog
- [ ] Standalone .app packaging

### Nice to Have (Post 1.0)
- [ ] External trigger input support
- [ ] TV trigger
- [ ] XY display mode
- [ ] Persistence display
- [ ] Segmented memory
- [ ] LAN bridge mode
- [ ] Additional protocol decoders (CAN, LIN, 1-Wire)
- [ ] Plugin system for community hardware drivers
- [ ] Waveform math (CH1+CH2, CH1-CH2)
- [ ] Mask testing
- [ ] Power analysis
