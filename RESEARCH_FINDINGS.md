# Research Findings: Agilent U2702A on macOS

> Combined findings from ChatGPT research, Claude web research, and cross-referencing.
> Last updated: 2026-03-04

---

## 1. Device Specifications

| Parameter | Value |
|---|---|
| Model | U2702A (U2700A series) |
| Bandwidth | DC to 200 MHz (-3 dB) |
| Channels | 2 analog |
| Vertical Resolution | 8 bits |
| Sample Rate (interleaved) | 1 GSa/s |
| Sample Rate (per channel) | 500 MSa/s |
| Memory Depth (interleaved) | Normal 32 Mpts / Single-shot 64 Mpts |
| Memory Depth (per channel) | Normal 16 Mpts / Single-shot 32 Mpts |
| Rise Time | 1.75 ns |
| Input Impedance | 1 MOhm |
| Input Voltage | CAT I 30 Vrms |
| Timebase Accuracy | 20 ppm |
| Interpolation | Sin(x)/x (1 ns to 100 ns timebase) |
| Averaging | 1 to 999 |
| Triggering | Edge, Pulse Width, TV |
| Math Functions | 4 including FFT |
| Connectivity | Hi-Speed USB 2.0 (480 Mbit/s), USBTMC-USB488 |
| Size | 117 mm x 180 mm x 41 mm |
| Weight | 534 g |
| Power | +12 VDC, 2 A |
| Status | **Discontinued** June 1, 2024 (5 years support continues) |

---

## 2. USB Identifiers

| Field | Value |
|---|---|
| Vendor ID (VID) | `0x0957` (Agilent Technologies) |
| Product ID (PID) - Normal | `0x2918` |
| Product ID (PID) - Firmware Update Mode | `0x2818` |
| USB Class | USBTMC-USB488 |
| USB Speed | Hi-Speed USB 2.0 (480 Mbit/s) |

Note: PID `0xFB18` seen in some databases is an LC device, NOT the U2702A.

---

## 3. CRITICAL FINDING: SCPI Commands Situation

### Official Position: No SCPI
Keysight officially states the U2702A can ONLY be programmed via IVI-COM/IVI-C drivers (Windows-only).
Source: https://docs.keysight.com/kkbopen/are-there-any-programming-commands-for-the-u2701a-u2702a-usb-modular-oscilloscope-589737250.html

### Undocumented Reality: SCPI Commands DO Exist
**This is the most important finding from our research.**

Community members on Keysight forums discovered that by using **IO Monitor** (from Agilent IO Library Suite) while running Agilent Measurement Manager (AMM), you can observe SCPI commands being sent to the device. These undocumented SCPI commands **work when used programmatically** via VISA in MATLAB and C++.

Source: https://community.keysight.com/thread/7220

**This means the device DOES speak SCPI internally; Keysight simply never documented the command set.**

### Implication
If we can capture the complete SCPI command set via IO Monitor sniffing, we can potentially control the U2702A from macOS using PyVISA + pyvisa-py, bypassing the need for the Windows-only IVI-COM driver entirely.

---

## 4. macOS Compatibility: Official Status

| Component | Mac Support |
|---|---|
| Keysight IO Libraries Suite | NO (Windows + Linux only) |
| Keysight Connection Expert | NO (Windows, Windows ARM, Linux only) |
| BenchVue Desktop | NO (Windows only) |
| IVI-COM/IVI-C Drivers | NO (Windows only) |
| BenchVue Mobile (iOS/macOS) | Partial - needs Windows BenchVue as bridge |
| Keysight Oscilloscope Mobile | Partial - LAN-connected scopes only, not USB |

---

## 5. PyVISA / pyvisa-py on macOS

### General Setup (works for other instruments)
```
pip install pyvisa pyvisa-py pyusb
brew install libusb
```

### U2702A-Specific Problems
1. **No official SCPI** -- but undocumented SCPI exists (see section 3)
2. **Firmware initialization** -- device may need Windows "jump-start" via AMM before working on other platforms
3. **Pipe errors** -- `usb.core.USBError: [Errno 32] Pipe error` when querying serial number
4. **macOS USB timeouts** -- `[Errno 60] Operation timed out` reported on macOS

Sources:
- https://github.com/python-ivi/python-usbtmc/issues/31
- https://github.com/python-ivi/python-usbtmc/issues/27
- https://github.com/python-ivi/python-usbtmc/issues/58

---

## 6. IVI-COM Driver Details (Windows Reference)

| Detail | Value |
|---|---|
| Driver Version | 1.3.5.0 (latest) |
| Driver Type | IVI-COM and IVI-C |
| Supported OS | Windows 7/Vista/XP SP3/10 (32+64 bit) |
| Prerequisites | Keysight IO Libraries Suite + VISA |

### Key IVI-COM API Methods
| Method | Description |
|---|---|
| `ReadWaveform` | Reads 1250 waveform data points |
| `ReadFullWaveform` | Reads full memory depth (up to 32 Mpts) |
| `ConfigureChannel` | Configure channel settings |
| `AcquisitionType` | Set acquisition mode |

### Programming References
- IVI-COM Reference Guide: https://www.keysight.com/us/en/lib/resources/release-notes/usb-modular-scopes-programmers-reference-guide-ivicom-1507892.html
- LabVIEW Reference: https://pim-resources.coleparmer.com/data-sheet/cm-58042-labview-programmers-reference.pdf
- MATLAB Example: https://www.mathworks.com/matlabcentral/fileexchange/23958
- VEE Reference: https://pim-resources.coleparmer.com/data-sheet/cm-58042-vee-programmers-reference.pdf

---

## 7. Existing Open-Source Projects (Ranked by Relevance)

### A. Direct U2702A Attempts
| Project | Result |
|---|---|
| python-usbtmc Issue #31 | Device detected but pipe errors on communication |
| python-ivi | Has `agilentBaseScope.py` but no U2702A-specific driver |
| sigrok/PulseView | NOT supported |
| OpenHantek | NOT compatible (Hantek hardware only) |

### B. Best Reference Projects for Our GUI

1. **HaasoscopePro** (Best architecture reference)
   - Repo: https://github.com/drandyhaas/HaasoscopePro
   - Stack: Python, PyQt5, pyqtgraph, numpy, scipy
   - Features: Real-time waveform, persistence/heatmap, FFT, filtering, trigger GUI
   - Why relevant: Most sophisticated open-source Python scope GUI

2. **Interfacing-an-Oscilloscope-Using-Python** (Best starting template)
   - Repo: https://github.com/god233012yamil/Interfacing-an-Oscilloscope-Using-Python
   - Stack: PyQt5, PyVISA, Matplotlib
   - Features: Dynamic UI, real-time waveform, channel/timebase/voltage/trigger controls
   - Why relevant: Clean architecture, easy to adapt

3. **oscope-scpi** (Best SCPI library reference)
   - Repo: https://github.com/sgoadhouse/oscope-scpi
   - Stack: Python, PyVISA (with pyvisa-py)
   - Features: Screen capture, waveform data retrieval for Keysight scopes

4. **SoftwareOscilloscope** (Best generic data stream visualizer)
   - Repo: https://github.com/suyashb95/SoftwareOscilloscope
   - Stack: Python, PyQtGraph
   - Features: Real-time plotting from any data stream

5. **dualscope123** (Best analog-scope-like UI reference)
   - Repo: https://github.com/ggventurini/dualscope123
   - Features: Knob-based UI, spectrum analyzer, trace averaging

### C. Other Relevant Projects
- keyoscacquire: https://pypi.org/project/keysightoscilloscopeacquire/
- ScopeOut: https://github.com/SeanMcGrath/ScopeOut
- KeysightPy: https://github.com/Rin-0xTohsaka/KeysightPy
- pglive (thread-safe live pyqtgraph): https://pypi.org/project/pglive/

---

## 8. GUI Framework Decision

| Framework | FPS | Ease | Real-Time | Notes |
|-----------|-----|------|-----------|-------|
| **PyQtGraph + PySide6** | 1000+ | Moderate | Outstanding | **OUR CHOICE** |
| Matplotlib + PyQt | ~40 | Easy | Adequate for slow signals | Too slow |
| Tkinter | Low | Easy | Poor | Not suitable |
| Qt/C++ + OpenGL | Best | Hard | Outstanding | Overkill for Python |
| VisPy (GPU) | Very High | Moderate | Outstanding | Alternative option |

**Decision: PySide6 + PyQtGraph** (user preference for Qt6)

---

## 9. Reverse Engineering Approaches

### Approach A: IO Monitor Sniffing (RECOMMENDED - Easiest)
1. Install Agilent IO Library Suite on Windows (or Windows VM)
2. Run Agilent Measurement Manager (AMM)
3. Open IO Monitor to capture SCPI commands
4. Record ALL commands for: init, config, acquisition, data transfer
5. **Confirmed to work by Keysight community members**

### Approach B: USB Traffic Capture (Wireshark)
- Windows: USBPcap + Wireshark
- Linux: usbmon kernel module
- macOS: Requires disabling SIP (not recommended)
- Technique: Run AMM in Windows VM, capture USB on host
- Reference: https://hackaday.com/2021/02/09/reverse-engineering-usb-protocols-on-a-function-generator/

### Approach C: IVI-COM DLL Analysis
- Decompile IVI-COM DLLs to understand command structure
- AMM includes Command Logger and Code Converter tools

### Related: Agilent PCIe Analyzer RE
- Repo: https://github.com/cyrozap/agilent-pcie-analyzer-re
- Methodology reference for Agilent hardware RE

---

## 10. Realistic Options for macOS (Ranked)

### Option 1: SCPI Sniffing + Native macOS (BEST if SCPI works)
1. Sniff SCPI commands via IO Monitor on Windows/VM
2. Use PyVISA + pyvisa-py + libusb on macOS
3. Build native PySide6 GUI
4. **Risk**: Device may still need Windows "jump-start"

### Option 2: Windows VM Bridge (MOST RELIABLE)
1. Run Windows VM with IVI driver
2. Create TCP/JSON-RPC bridge server on Windows side
3. macOS GUI connects via network to bridge
4. Full compatibility guaranteed

### Option 3: Direct USB with PyUSB (EXPERIMENTAL)
1. Use PyUSB + libusb to send raw USB commands
2. Requires full protocol reverse engineering
3. Most work, but most native result

### Option 4: Hybrid Approach (RECOMMENDED STARTING POINT)
1. Start with Option 1 (SCPI sniffing)
2. If device needs jump-start, add VM bridge for init only
3. Once initialized, communicate directly from macOS
4. Fall back to Option 2 if direct comms fail

---

## 11. Cross-Reference: ChatGPT vs Claude Findings

| Topic | ChatGPT Finding | Claude Finding | Resolution |
|---|---|---|---|
| SCPI Support | "No SCPI, vendor-specific protocol" | **Undocumented SCPI exists, confirmed by community** | Claude finding is more complete |
| macOS drivers | "No native drivers" | Same + confirmed IO Libraries Linux-only, no Mac | Aligned |
| python-usbtmc | "Failed, USB errors" | Same + identified specific PIDs and firmware mode | Aligned, Claude more detailed |
| Open-source support | "No existing support" | Same, confirmed sigrok/OpenHantek don't support it | Aligned |
| Best approach | "Reverse engineer or VM proxy" | IO Monitor SCPI sniffing as easiest RE path | Claude found concrete method |
| GUI stack | "PyQt5 + PyQtGraph" | **PySide6 + PyQtGraph** (user preference) | Updated to Qt6 |

---

## 12. Key Resources

| Resource | URL |
|---|---|
| Keysight U2702A Support | https://www.keysight.com/us/en/support/U2702A/ |
| Datasheet PDF | https://www.keysight.com/us/en/assets/7018-03265/data-sheets/5990-9537.pdf |
| IVI Drivers Download | https://www.keysight.com/us/en/lib/software-detail/driver/u2701a-u2702a-usb-modular-oscilloscope-ivi-instrument-drivers-1540317.html |
| Keysight Community SCPI Thread | https://community.keysight.com/thread/7220 |
| python-usbtmc (U2702A issue) | https://github.com/python-ivi/python-usbtmc/issues/31 |
| python-usbtmc (Mac setup) | https://github.com/python-ivi/python-usbtmc/issues/13 |
| PyVISA Docs | https://pyvisa.readthedocs.io/ |
| PyVISA-py Docs | https://pyvisa.readthedocs.io/projects/pyvisa-py/en/latest/ |
| PyQtGraph | https://pyqtgraph.com/ |
| HaasoscopePro | https://github.com/drandyhaas/HaasoscopePro |
| Oscilloscope Python GUI | https://github.com/god233012yamil/Interfacing-an-Oscilloscope-Using-Python |
| oscope-scpi | https://github.com/sgoadhouse/oscope-scpi |
| MATLAB Example | https://www.mathworks.com/matlabcentral/fileexchange/23958 |
| IVI-COM Reference | https://www.keysight.com/us/en/lib/resources/release-notes/usb-modular-scopes-programmers-reference-guide-ivicom-1507892.html |
| VEE Reference PDF | https://pim-resources.coleparmer.com/data-sheet/cm-58042-vee-programmers-reference.pdf |
| USB Wireshark Guide | https://wiki.wireshark.org/CaptureSetup/USB |
| Agilent RE Reference | https://github.com/cyrozap/agilent-pcie-analyzer-re |
