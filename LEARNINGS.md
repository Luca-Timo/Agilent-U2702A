# Learnings & Mistakes Log

> Add every mistake, dead end, and lesson learned here so we never repeat them.
> Format: Date | Category | What happened | What we learned

---

## Research Phase Mistakes

### 2026-03-04 | Wrong Assumption | SCPI not supported
**What happened:** Initial research (ChatGPT) concluded the U2702A has no SCPI support at all, only IVI-COM. This almost led us to abandon the PyVISA approach entirely.
**What we learned:** Always dig deeper into community forums. Keysight community members confirmed undocumented SCPI commands exist and work. The official docs don't tell the whole story. **Always check vendor community forums, not just official docs.**

### 2026-03-04 | Wrong Framework | PyQt5 recommended initially
**What happened:** Multiple reference projects and initial research recommended PyQt5. User wants PySide6 (Qt6).
**What we learned:** Always confirm framework preferences with user before recommending. PySide6 is the official Qt for Python binding and is more permissively licensed (LGPL vs GPL for PyQt). Use PySide6 going forward.

### 2026-03-04 | Wrong PID | USB Product ID confusion
**What happened:** Some USB ID databases list PID `0xFB18` for Agilent devices. This is NOT the U2702A -- it's a Liquid Chromatography device.
**What we learned:** The correct PIDs are `0x2918` (normal mode) and `0x2818` (firmware update mode). Always verify USB IDs against actual device enumeration, not just databases.

### 2026-03-04 | Dead End | sigrok/PulseView
**What happened:** Investigated whether sigrok supports the U2702A.
**What we learned:** It does not. sigrok's Agilent support is limited to DSO1000 series (rebadged Rigol). Don't waste time trying to add sigrok support -- the effort would be enormous for a proprietary protocol device.

### 2026-03-04 | Dead End | OpenHantek adaptation
**What happened:** Considered adapting OpenHantek6022 for the U2702A.
**What we learned:** OpenHantek is deeply tied to Hantek/FX2 hardware architecture (firmware upload model). The U2702A has its own firmware and a completely different protocol. Adapting OpenHantek would be more work than building from scratch.

### 2026-03-04 | Dead End | Matplotlib for real-time display
**What happened:** Some reference projects use Matplotlib for waveform display.
**What we learned:** Matplotlib maxes out at ~40 FPS. PyQtGraph achieves 1000+ FPS. For an oscilloscope GUI, PyQtGraph is the only viable choice for real-time display.

---

## Development Phase Mistakes

(Add entries here as development progresses)

<!-- Template:
### YYYY-MM-DD | Category | Short title
**What happened:** Description of the mistake or dead end.
**What we learned:** The lesson and what to do differently.
-->

---

## Quick Reference: Things That DON'T Work

| Approach | Why It Fails |
|---|---|
| Standard SCPI via PyVISA (without sniffing) | Commands are undocumented, `*IDN?` may not work |
| sigrok / PulseView | U2702A not supported |
| OpenHantek | Wrong hardware architecture |
| Matplotlib real-time | Too slow (40 FPS) |
| NI-VISA on macOS | Not strictly needed, pyvisa-py works |
| python-usbtmc directly | Pipe errors, device doesn't enumerate properly |
| BenchVue on macOS | Windows only |
| IVI-COM on macOS | Windows DLL, cannot run on Mac |
| PID 0xFB18 | Wrong device (LC, not oscilloscope) |

---

## Quick Reference: Things That DO Work

| Approach | Status |
|---|---|
| IO Monitor SCPI sniffing on Windows | Confirmed by community |
| Sniffed SCPI commands via VISA | Confirmed working in MATLAB/C++ |
| PyVISA + pyvisa-py + libusb on macOS | Works for USBTMC devices in general |
| PyQtGraph for real-time waveform | 1000+ FPS, proven in HaasoscopePro |
| PySide6 for GUI | Modern, actively maintained, LGPL |
| NumPy/SciPy for signal processing | Industry standard |
