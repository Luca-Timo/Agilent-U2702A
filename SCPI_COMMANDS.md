# SCPI Command Reference: U2702A

> Captured from USB traffic analysis (Wireshark/USBPcap on Windows host).
> Source files:
>   - `USB_dump_ch1_2_single.pcapng` — CH1/CH2 basic ops, single acquisitions
>   - `USB_dump_2_all_funct.pcapng` — all AMM functions exercised
> Extracted using `parse_usb_capture.py` (tshark + Python).
> Last updated: 2026-03-06

---

## Device Identity

```
*IDN? -> AGILENT TECHNOLOGIES,U2702A,MY50032044,V2.47-2.05-1.05
```

| Field | Value |
|---|---|
| Manufacturer | AGILENT TECHNOLOGIES |
| Model | U2702A |
| Serial | MY50032044 |
| Firmware | V2.47-2.05-1.05 |

---

## Capture Summary

| Metric | Capture 1 | Capture 2 |
|---|---|---|
| File | `USB_dump_ch1_2_single.pcapng` | `USB_dump_2_all_funct.pcapng` |
| Duration | 160.4s | 240.3s |
| SCPI exchanges | 12,004 | 31,502 |
| Unique commands | 52 | 61 |
| Probe | 10:1 passive on test signal | 10:1 passive on test signal |

---

## Initialization Sequence

AMM sends `*IDN?` first, then this sequence on every connection:

```
1.  *CLS                           # Clear status registers
2.  ACQ:TYPE?                      # -> "NORM"
3.  TIM:MODE?                      # -> "MAIN"
4.  TIMEBASE:POS?                  # -> +0.00000000E+00
5.  TIM:RANG?                      # -> +1.00E-08
6.  TIM:REF?                       # -> "CENT"
7.  TIM:SCAL?                      # -> +1.00E-09
8.  TIMEBASE:POS 0.000000E+000     # Set horizontal position to 0
9.  *OPC?                          # -> 1
10. FUNCTION:NOISEFLOOR?           # -> 0
11. TRIGGER:MODE?                  # -> "EDGE"
12. TRIGGER:HOLDOFF?               # -> +0.00000000E+00
13. TRIGGER:SWEEP?                 # -> "AUTO"
14. TRIGGER:NREJECT?               # -> 0
15. OUTPUT:TRIGGER:SOURCE?         # -> "NONE"
16. TRIGGER:EDGE:SOURCE?           # -> "CHAN1"
17. TRIGGER:EDGE:LEVEL?            # -> +0.00000000E+00
18. TRIGGER:EDGE:COUPLING?         # -> "DC"
19. TRIG:EDGE:SLOPE?               # -> "POS"
20. TRIGGER:GLITCH:POLARITY?       # -> "POS" or "NEG"
21. TRIGGER:GLITCH:QUALIFIER?      # -> "LESS"
22. TRIGGER:GLITCH:GRE?            # -> +3.00000000E-08
23. TRIGGER:GLITCH:LESS?           # -> +2.00000000E-08
24. TRIGGER:GLITCH:RANGE?          # -> +3.00E-08 ,+2.00E-08
25. TRIGGER:TV:MODE?               # -> "FIE1"
26. TRIGGER:TV:STANDARD?           # -> "NTSC"
27. TRIGGER:TV:LINE?               # -> +1
28. TRIGGER:TV:POLARITY?           # -> "NEG"
29. CHANNEL1:OFFSET?               # -> +0.000E+00
30. CHANNEL1:SCALE?                # -> +200E-03 (or +5.00E+00)
31. CHANNEL1:DISPLAY?              # -> 0
32. CHANNEL1:BWLIMIT?              # -> 0
33. CHANNEL1:COUPLING?             # -> "DC"
34. CHANNEL2:OFFSET?               # -> +0.000E+00
35. CHANNEL2:SCALE?                # -> +200E-03 (or +5.00E+00)
36. CHANNEL2:DISPLAY?              # -> 0
37. CHANNEL2:BWLIMIT?              # -> 0
38. CHANNEL2:COUPLING?             # -> "DC"
39. TRIGGER:SWEEP AUTO
40. *OPC?
41. FUNCTION:NOISEFLOOR OFF
42. TRIG:EDGE:SLOPE POS
```

---

## Captured Commands — Complete Reference

### System / IEEE 488.2

| Command | Description | Response |
|---|---|---|
| `*IDN?` | Device identity | `AGILENT TECHNOLOGIES,U2702A,MY50032044,V2.47-2.05-1.05` |
| `*CLS` | Clear status registers | (no response) |
| `*OPC?` | Operation complete query | `1` |

**Not yet captured:** `*RST`, `*CAL?`, `*TST?`

### Channel Configuration

| Command | Description | Response / Values |
|---|---|---|
| `CHANNEL{1,2}:DISPLAY?` | Query display state | `0` (off), `1` (on) |
| `CHANNEL{1,2}:DISPLAY ON` | Enable channel display | — |
| `CHANNEL{1,2}:SCALE?` | Query V/div | e.g. `+200E-03`, `+5.00E+00` |
| `CHANNEL{1,2}:SCALE <val>` | Set V/div | Scientific notation (see table below) |
| `CHANNEL{1,2}:OFFSET?` | Query vertical offset | e.g. `+0.000E+00` |
| `CHANNEL{1,2}:OFFSET <val>` | Set vertical offset (volts) | Scientific notation |
| `CHANNEL{1,2}:COUPLING?` | Query coupling | `DC`, `AC` |
| `CHANNEL{1,2}:COUPLING <val>` | Set coupling | `DC`, `AC` |
| `CHANNEL{1,2}:BWLIMIT?` | Query bandwidth limit | `0` (off), `1` (on) |
| `CHANNEL{1,2}:BWLIMIT <val>` | Set bandwidth limit | `ON`, `OFF` |

#### V/div Scale Values (Confirmed)

| V/div | SCPI Value | Observed |
|---|---|---|
| 2 mV | `2.000000E-003` | CH1 |
| 5 mV | `5.000000E-003` | CH1 |
| 10 mV | `1.000000E-002` | CH1, CH2 |
| 20 mV | `2.000000E-002` | CH1, CH2 |
| 50 mV | `5.000000E-002` | CH1, CH2 |
| 100 mV | `1.000000E-001` | CH1, CH2 |
| 200 mV | `2.000000E-001` | CH1, CH2 |
| 500 mV | `5.000000E-001` | CH1, CH2 |
| 1 V | `1.000000E+000` | CH1, CH2 |
| 2 V | `2.000000E+000` | CH1 |
| 5 V | `5.000000E+000` | CH1 |

Also observed non-standard intermediate values from AMM autoranging:
`2.500000E+000`, `1.250000E+000`, `6.250000E-001`, `3.125000E-001`

#### Offset Values (Observed)

Observed range: `-5.000000E-001` to `+1.500000E+000` (depends on V/div setting)

**Not yet captured:** `CHANNEL{1,2}:DISPLAY OFF`, `CHANNEL{1,2}:PROBE?`

### Timebase

| Command | Description | Response / Values |
|---|---|---|
| `TIM:MODE?` | Query mode | `MAIN` |
| `TIM:RANG?` | Query time range | e.g. `+1.00E-08` |
| `TIM:REF?` | Query reference point | `CENT` |
| `TIM:SCAL?` | Query time/div | e.g. `+1.00E-09` |
| `TIM:SCAL <val>` | Set time/div | Scientific notation (see below) |
| `TIMEBASE:POS?` | Query horizontal position | `+0.00000000E+00` |
| `TIMEBASE:POS <val>` | Set horizontal position | `TIMEBASE:POS 0.000000E+000` |

#### T/div Values

SCPI-confirmed (from capture) marked with ✓. Rest from AMM GUI.

| T/div | SCPI Value | Status |
|---|---|---|
| 1 ns | `1.000000E-009` | GUI (initial default in capture 2) |
| 2 ns | `2.000000E-009` | ✓ captured |
| 5 ns | `5.000000E-009` | ✓ captured |
| 10 ns | `1.000000E-008` | ✓ captured |
| 20 ns | `2.000000E-008` | ✓ captured |
| 50 ns | `5.000000E-008` | ✓ captured |
| 100 ns | `1.000000E-007` | ✓ captured |
| 200 ns | `2.000000E-007` | ✓ captured |
| 500 ns | `5.000000E-007` | ✓ captured |
| 1 us | `1.000000E-006` | ✓ captured |
| 2 us | `2.000000E-006` | GUI |
| 5 us | `5.000000E-006` | GUI |
| 10 us | `1.000000E-005` | GUI |
| 20 us | `2.000000E-005` | GUI |
| 50 us | `5.000000E-005` | GUI |
| 100 us | `1.000000E-004` | GUI |
| 200 us | `2.000000E-004` | GUI |
| 500 us | `5.000000E-004` | GUI |
| 1 ms | `1.000000E-003` | GUI |
| 2 ms | `2.000000E-003` | GUI |
| 5 ms | `5.000000E-003` | GUI |
| 10 ms | `1.000000E-002` | GUI |
| 20 ms | `2.000000E-002` | GUI |
| 50 ms | `5.000000E-002` | GUI |
| 100 ms | `1.000000E-001` | GUI |
| 200 ms | `2.000000E-001` | GUI |
| 500 ms | `5.000000E-001` | GUI |
| 1 s | `1.000000E+000` | GUI |
| 2 s | `2.000000E+000` | GUI |
| 5 s | `5.000000E+000` | GUI |
| 10 s | `1.000000E+001` | GUI |
| 20 s | `2.000000E+001` | GUI |
| 50 s | `5.000000E+001` | GUI |
| 60 s | `6.000000E+001` | GUI |
| 120 s | `1.200000E+002` | GUI |
| 300 s | `3.000000E+002` | GUI |
| 600 s | `6.000000E+002` | GUI |
| 1.2 ks | `1.200000E+003` | GUI |

**Notes:**
- `TIM:SCAL` always followed by `TIMEBASE:POS 0.000000E+000`
- Time range = 10 * time/div (10 divisions)
- Long form `TIMEBASE:` and short form `TIM:` both work
- 1-50s follows 1/2/5 sequence; above 50s uses 60/120/300/600/1200

### Trigger

#### Trigger Type

| Command | Description | Values |
|---|---|---|
| `TRIGGER:MODE?` | Query trigger type | `EDGE`, `GLIT`, `TV` |
| `TRIGGER:MODE <val>` | Set trigger type | `EDGE`, `GLIT`, `TV` |

#### Edge Trigger

| Command | Description | Values |
|---|---|---|
| `TRIGGER:EDGE:SOURCE?` | Query source | `CHAN1`, `CHAN2`, `EXT` |
| `TRIGGER:EDGE:SOURCE <val>` | Set source | `CHAN1`, `CHAN2`, `EXT` |
| `TRIGGER:EDGE:LEVEL?` | Query level (volts) | e.g. `+0.00000000E+00` |
| `TRIGGER:EDGE:LEVEL <val>` | Set level | e.g. `0.000000E+000` |
| `TRIG:EDGE:SLOPE?` | Query slope | `POS`, `NEG`, `EITH`, `ALT` |
| `TRIG:EDGE:SLOPE <val>` | Set slope | `POS`, `NEG`, `EITH`, `ALT` |
| `TRIGGER:EDGE:COUPLING?` | Query coupling | `DC`, `AC`, `LFR`, `HFR` |
| `TRIGGER:EDGE:COUPLING <val>` | Set coupling | `DC`, `AC`, `LFR`, `HFR` |

**Slope values:**
- `POS` — rising edge
- `NEG` — falling edge
- `EITH` — either edge
- `ALT` — alternating

**Coupling values:**
- `DC` — DC coupling
- `AC` — AC coupling
- `LFR` — low frequency reject
- `HFR` — high frequency reject

#### Trigger Sweep Mode

| Command | Description | Values |
|---|---|---|
| `TRIGGER:SWEEP?` | Query sweep mode | `AUTO`, `NORM` |
| `TRIGGER:SWEEP <val>` | Set sweep mode | `AUTO`, `NORM` |
| `TRIGGER:HOLDOFF?` | Query holdoff | e.g. `+0.00000000E+00` |
| `TRIGGER:HOLDOFF <val>` | Set holdoff (seconds) | e.g. `6.000000E-008` |
| `TRIGGER:NREJECT?` | Query noise reject | `0` (off) |
| `OUTPUT:TRIGGER:SOURCE?` | Query trigger output | `NONE` |

#### Glitch (Pulse Width) Trigger

| Command | Description | Values |
|---|---|---|
| `TRIGGER:GLITCH:POLARITY?` | Query polarity | `POS`, `NEG` |
| `TRIGGER:GLITCH:POLARITY <val>` | Set polarity | `POS` |
| `TRIGGER:GLITCH:QUALIFIER?` | Query qualifier | `LESS`, `GRE`, `RANG`, `OUTRANG` |
| `TRIGGER:GLITCH:QUALIFIER <val>` | Set qualifier | `LESS`, `GRE`, `RANG`, `OUTRANG` |
| `TRIGGER:GLITCH:GRE?` | Query greater-than | e.g. `+3.00000000E-08` |
| `TRIGGER:GLITCH:LESS?` | Query less-than | e.g. `+2.00000000E-08` |
| `TRIGGER:GLITCH:RANGE?` | Query range | e.g. `+3.00E-08 ,+2.00E-08` |

**Qualifier values:**
- `LESS` — pulse width less than threshold
- `GRE` — pulse width greater than threshold
- `RANG` — pulse width within range
- `OUTRANG` — pulse width outside range

#### TV Trigger

| Command | Description | Values |
|---|---|---|
| `TRIGGER:TV:MODE?` | Query TV mode | `FIE1` |
| `TRIGGER:TV:STANDARD?` | Query TV standard | `NTSC` |
| `TRIGGER:TV:LINE?` | Query line number | `+1` |
| `TRIGGER:TV:POLARITY?` | Query polarity | `NEG` |

### Acquisition Control

| Command | Description | Notes |
|---|---|---|
| `ACQ:TYPE?` | Query acquisition type | `NORM` |
| `:RUN` | Start continuous acquisition | Leading colon required! |
| `:STOP` | Stop acquisition | Leading colon required! |
| `:SINGLE` | Single acquisition | Leading colon required! |

**Important:** `:RUN`, `:STOP`, `:SINGLE` use a leading colon.

### Waveform Data Transfer

| Command | Description | Notes |
|---|---|---|
| `WAV:DATA?` | Read waveform data | IEEE 488.2 binary block |

#### Channel Source Selection

| Command | Description | Result |
|---|---|---|
| `WAV:SOUR CHAN1` | Select CH1 for data readout | **Accepted** (no timeout) |
| `WAV:SOUR CHAN2` | Select CH2 for data readout | **Accepted** (no timeout) |
| `WAV:SOUR?` | Query current source | **TIMEOUT** — query form does not exist |
| `WAV:SOURCE` (bare) | — | **TIMEOUT** — does not exist |

**Usage:** Send `WAV:SOUR CHANx` before `:SINGLE` + `WAV:DATA?` to select which channel's data is returned.

**Confirmed via Interactive IO: the following commands DO NOT EXIST on this device**
(all return `VI_ERROR_TMO` timeout):

- `WAV:PREAMBLE?` / `WAV:PRE?` — no waveform metadata
- `WAV:SOUR?` — query form of source selection does not exist (but SET form `WAV:SOUR CHANx` works!)
- `WAV:FORMAT`, `WAV:POINTS` — not tested but assumed absent
- `MEAS:VPP?` — no on-device measurements
- `CHANNEL1:PROBE?` — no probe attenuation via SCPI
- `*RST` — no device reset

Voltage conversion must be calculated from known SCALE and OFFSET settings.
Probe factor is tracked in software only.

### Function / Math

| Command | Description | Values |
|---|---|---|
| `FUNCTION:NOISEFLOOR?` | Query noise floor | `0` (off) |
| `FUNCTION:NOISEFLOOR OFF` | Disable noise floor | — |

---

## Waveform Data Format (CONFIRMED)

### IEEE 488.2 Binary Block

```
#8NNNNNNNN<data>
```

- `#8` = definite-length block, 8-digit byte count
- `NNNNNNNN` = ASCII byte count of data payload

### Empty/Polling Response

```
#800000002 + 0x30 0x30 + LF
```
= "no data ready" (2 bytes of ASCII "00")

### Waveform Data Response

```
#800002514 + <2 prefix bytes> + <2512 ADC samples>
```

- Total IEEE payload: 2514 bytes
- Prefix: 2 status/flag bytes (byte 0 varies, byte 1 always 0x00)
- ADC data: 2512 bytes split into two halves:
  - Bytes 0–1255 (1256 bytes): selected channel ADC data
  - Bytes 1256–2511 (1256 bytes): zeros (padding or inactive channel)

### Data Structure Detail

```
[2 prefix] [1256 bytes: channel data] [1256 bytes: 0x00 padding]
```

- Use `WAV:SOUR CHAN1` or `WAV:SOUR CHAN2` before acquisition to select channel
- Only the first 1256 bytes contain valid ADC samples
- The second 1256 bytes are always `0x00` in all tests so far
- **Points per channel per transfer: 1256**

### ADC Data Format

| Property | Value |
|---|---|
| Resolution | 8-bit unsigned (0-255) |
| Center value | 128 (0x80) = 0V at current offset |
| Points per channel | 1256 |
| Raw transfer size | 2512 (1256 active + 1256 padding) |
| Update rate (RUN) | ~30 Hz (~33ms per transfer) |
| Transfers per SINGLE | 1 |

### Voltage Conversion

Since WAV:PREAMBLE is not available, compute voltage from known settings:

```python
# 8 vertical divisions, 8-bit ADC (256 levels)
v_per_div = float(scope.query('CHANNEL1:SCALE?'))
offset = float(scope.query('CHANNEL1:OFFSET?'))
probe_ratio = 10  # for 10:1 probe

y_increment = (8 * v_per_div) / 256
voltage = (raw_adc - 128) * y_increment + offset
display_voltage = voltage * probe_ratio  # actual voltage at probe tip
```

### Prefix Bytes

The 2 bytes before ADC data are status flags. Byte 0 observed values:
`0x00`, `0x01` (most common), `0x02`, `0x03`, `0x04`, `0x06`.
Byte 1 is always `0x00`. Exact meaning TBD.

---

## Operational Patterns

### Continuous Acquisition

```
:RUN
loop:
    WAV:DATA? -> #800000002 + "00"    (polling, ~8-10x)
    WAV:DATA? -> #800002514 + data    (waveform, every ~33ms)
:STOP
```

### Single Acquisition

```
:SINGLE
WAV:DATA? -> #800000002 + "00"    (polling, ~10x)
WAV:DATA? -> #800002514 + data    (single waveform)
```

### Two-Channel Acquisition

```
WAV:SOUR CHAN1
:SINGLE
WAV:DATA? -> (poll until ready)
WAV:DATA? -> #800002514 + [2 prefix][1256 CH1 data][1256 zeros]

WAV:SOUR CHAN2
:SINGLE
WAV:DATA? -> (poll until ready)
WAV:DATA? -> #800002514 + [2 prefix][1256 CH2 data][1256 zeros]
```

Each channel requires a separate `:SINGLE` + `WAV:DATA?` cycle.

### Setting a Parameter

```
CHANNEL1:SCALE 1.000000E+000
*OPC?                              # Always wait for completion
```

---

## Sniffing Checklist

- [x] Device identity — `*IDN?` captured
- [x] Channel enable — `CHANNEL{1,2}:DISPLAY ON`
- [x] Vertical scale — `CHANNEL{1,2}:SCALE` (2mV to 5V confirmed)
- [x] Vertical offset — `CHANNEL{1,2}:OFFSET`
- [x] Coupling — `CHANNEL{1,2}:COUPLING DC|AC`
- [x] Bandwidth limit — `CHANNEL{1,2}:BWLIMIT ON|OFF`
- [x] Timebase set — `TIM:SCAL` (2ns to 1us confirmed)
- [x] Timebase position — `TIMEBASE:POS`
- [x] Trigger type — `TRIGGER:MODE EDGE|GLIT|TV`
- [x] Trigger source — `TRIGGER:EDGE:SOURCE CHAN1|CHAN2|EXT`
- [x] Trigger slope — `TRIG:EDGE:SLOPE POS|NEG|EITH|ALT`
- [x] Trigger coupling — `TRIGGER:EDGE:COUPLING DC|AC|LFR|HFR`
- [x] Trigger level — `TRIGGER:EDGE:LEVEL`
- [x] Trigger sweep — `TRIGGER:SWEEP AUTO|NORM`
- [x] Trigger holdoff — `TRIGGER:HOLDOFF`
- [x] Glitch trigger — full qualifier/polarity/range
- [x] TV trigger — mode/standard/line/polarity queries
- [x] Acquisition — `:RUN`, `:STOP`, `:SINGLE`
- [x] Waveform data — `WAV:DATA?` with IEEE 488.2 binary block
- [x] Data format verified — 8-bit unsigned, 2512 samples, ~30 Hz
- [ ] Channel disable — `CHANNEL{1,2}:DISPLAY OFF` (not observed, but likely works)
- [x] WAV:PREAMBLE — **DOES NOT EXIST** (confirmed via Interactive IO, timeout)
- [x] WAV:SOUR — **SET form works** (`WAV:SOUR CHAN1`/`CHAN2`), **query form `WAV:SOUR?` DOES NOT EXIST**
- [x] Measurement SCPI — **DOES NOT EXIST** (confirmed via Interactive IO, timeout)
- [x] Probe attenuation — **DOES NOT EXIST** (confirmed via Interactive IO, timeout)
- [x] *RST — **DOES NOT EXIST** (confirmed via Interactive IO, timeout)
- [ ] T/div > 1us — known from GUI, not SCPI-confirmed
- [ ] Commands tested from macOS via pyvisa-py

---

## Interactive IO Test Results (2026-03-06)

Tested via Keysight Connection Expert Interactive IO.
Connection: `USB0::0x0957::0x2918::MY50032044::0::INSTR`

| Command | Result |
|---|---|
| `*IDN?` | `AGILENT TECHNOLOGIES,U2702A,MY50032044,V2.47-2.05-1.05` |
| `WAV:PREAMBLE?` | **TIMEOUT** — does not exist |
| `WAV:PRE?` | **TIMEOUT** — does not exist |
| `WAV:SOURCE` (bare) | **TIMEOUT** — does not exist |
| `WAV:SOUR?` (query) | **TIMEOUT** — does not exist |
| `WAV:SOUR CHAN1` (set) | **ACCEPTED** — no timeout, selects CH1 |
| `WAV:SOUR CHAN2` (set) | **ACCEPTED** — no timeout, selects CH2 |
| `MEAS:VPP?` | **TIMEOUT** — does not exist |
| `CHANNEL1:PROBE?` | **TIMEOUT** — does not exist |
| `*RST` | **TIMEOUT** — does not exist |

**Conclusion:** The U2702A has a minimal SCPI command set. It does NOT support
waveform preamble, measurements, probe control, or reset via SCPI.
Channel source selection works via `WAV:SOUR CHANx` (set form only, no query).
All other missing features must be handled in software.
