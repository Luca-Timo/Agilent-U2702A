# U2702A — Next Capture Testing Steps

Follow these steps on the Windows machine with the U2702A connected.
Start Wireshark/USBPcap capture before each test, or use IO Monitor.

---

## Test 1: Device Identity & Reset

**Goal:** Capture `*IDN?` and `*RST`

In AMM or a Python/MATLAB terminal with VISA:
1. Open a VISA connection to the U2702A
2. Send `*IDN?` and record the response
3. Send `*RST` and record any response
4. Send `*IDN?` again to confirm device is still responding

If using Python on Windows:
```python
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())
scope = rm.open_resource('USB0::0x0957::0x2918::SERIALNUM::INSTR')
print(scope.query('*IDN?'))
scope.write('*RST')
print(scope.query('*OPC?'))
scope.close()
```

---

## Test 2: Waveform Preamble (MOST IMPORTANT)

**Goal:** Capture `WAV:PREAMBLE?` — this tells us how to convert raw ADC to volts

1. Enable CH1, set 1V/div
2. Connect a known signal (e.g. scope's cal output if available, or a function generator)
3. Try these commands one at a time:

```python
# Try different command variations (we don't know the exact syntax):
for cmd in ['WAV:PRE?', 'WAV:PREAMBLE?', 'WAVEFORM:PREAMBLE?',
            'WAV:XINC?', 'WAV:YINC?', 'WAV:XORG?', 'WAV:YORG?',
            'WAV:XREF?', 'WAV:YREF?', 'WAV:POINTS?', 'WAV:FORMAT?',
            'WAV:TYPE?', 'WAV:COUNT?']:
    try:
        resp = scope.query(cmd)
        print(f'{cmd} -> {resp}')
    except Exception as e:
        print(f'{cmd} -> ERROR: {e}')
```

Record ALL responses — even errors tell us something.

---

## Test 3: Waveform Source Selection

**Goal:** Find out how to select CH1 vs CH2 for WAV:DATA?

1. Enable both CH1 and CH2
2. Try these commands:

```python
for cmd in ['WAV:SOUR?', 'WAV:SOURCE?', 'WAVEFORM:SOURCE?',
            'WAV:SOUR CHAN1', 'WAV:SOURCE CHAN1',
            'WAV:SOUR CHAN2', 'WAV:SOURCE CHAN2',
            'WAV:SOUR CHANNEL1', 'WAV:SOUR CHANNEL2']:
    try:
        resp = scope.query(cmd) if cmd.endswith('?') else scope.write(cmd)
        print(f'{cmd} -> {resp}')
    except Exception as e:
        print(f'{cmd} -> ERROR: {e}')
```

After setting source to CHAN1, do `WAV:DATA?` and save the response.
After setting source to CHAN2, do `WAV:DATA?` and save the response.
Compare the data.

---

## Test 4: V/div Scale Values

**Goal:** Capture all vertical scale settings

1. Enable CH1
2. Run through each V/div setting in AMM (with Wireshark running), OR:

```python
scales = ['5E-3', '1E-2', '2E-2', '5E-2', '1E-1', '2E-1', '5E-1',
          '1E+0', '2E+0', '5E+0']
for s in scales:
    try:
        scope.write(f'CHANNEL1:SCALE {s}')
        print(scope.query('*OPC?'))
        actual = scope.query('CHANNEL1:SCALE?')
        print(f'Set {s} -> Read back: {actual}')
    except Exception as e:
        print(f'CHANNEL1:SCALE {s} -> ERROR: {e}')
```

---

## Test 5: T/div Timebase Values

**Goal:** Capture all timebase settings

```python
timescales = ['5E-9', '1E-8', '2E-8', '5E-8', '1E-7', '2E-7', '5E-7',
              '1E-6', '2E-6', '5E-6', '1E-5', '2E-5', '5E-5',
              '1E-4', '2E-4', '5E-4', '1E-3', '2E-3', '5E-3',
              '1E-2', '2E-2', '5E-2', '1E-1', '2E-1', '5E-1', '1E+0']
for t in timescales:
    try:
        scope.write(f'TIM:SCAL {t}')
        print(scope.query('*OPC?'))
        actual = scope.query('TIM:SCAL?')
        print(f'Set {t} -> Read back: {actual}')
    except Exception as e:
        print(f'TIM:SCAL {t} -> ERROR: {e}')
```

If `TIM:SCAL` doesn't work for setting, try `TIMEBASE:SCALE` or `TIM:RANG`.

---

## Test 6: AC Coupling & Bandwidth Limit

**Goal:** Capture coupling and BW limit set commands

```python
# Coupling
for val in ['AC', 'DC', 'GND']:
    try:
        scope.write(f'CHANNEL1:COUPLING {val}')
        actual = scope.query('CHANNEL1:COUPLING?')
        print(f'Set {val} -> {actual}')
    except Exception as e:
        print(f'COUPLING {val} -> ERROR: {e}')

# Bandwidth limit
for val in ['ON', 'OFF', '1', '0']:
    try:
        scope.write(f'CHANNEL1:BWLIMIT {val}')
        actual = scope.query('CHANNEL1:BWLIMIT?')
        print(f'Set {val} -> {actual}')
    except Exception as e:
        print(f'BWLIMIT {val} -> ERROR: {e}')
```

---

## Test 7: Probe Attenuation

**Goal:** Find probe attenuation commands

```python
for cmd in ['CHANNEL1:PROBE?', 'CHANNEL1:PROBE 1', 'CHANNEL1:PROBE 10',
            'CHAN1:PROB?', 'CHAN1:PROB 1', 'CHAN1:PROB 10',
            'CHANNEL1:PROBE:ATTENUATION?', 'CHANNEL1:PROBE:RATIO?']:
    try:
        resp = scope.query(cmd) if cmd.endswith('?') else scope.write(cmd)
        print(f'{cmd} -> {resp}')
    except Exception as e:
        print(f'{cmd} -> ERROR: {e}')
```

---

## Test 8: Measurement Commands

**Goal:** Check if device supports on-device measurements (or if AMM computes locally)

```python
for cmd in ['MEAS:VPP?', 'MEAS:VRMS?', 'MEAS:FREQ?', 'MEAS:PER?',
            'MEAS:RISETIME?', 'MEAS:FALLTIME?', 'MEAS:DUTYCYCLE?',
            'MEAS:VPP? CHAN1', 'MEAS:VRMS? CHAN1', 'MEAS:FREQ? CHAN1',
            'MEASURE:VPP?', 'MEASURE:VRMS?', 'MEASURE:FREQUENCY?',
            'MEAS:SOURCE?', 'MEAS:SOURCE CHAN1',
            'MEAS:VMAX?', 'MEAS:VMIN?', 'MEAS:VAVG?']:
    try:
        resp = scope.query(cmd) if cmd.endswith('?') else scope.write(cmd)
        print(f'{cmd} -> {resp}')
    except Exception as e:
        print(f'{cmd} -> ERROR: {e}')
```

---

## Test 9: Trigger Settings

**Goal:** Capture remaining trigger commands

```python
# Trigger slope
for val in ['POS', 'NEG', 'EITH', 'EITHER']:
    try:
        scope.write(f'TRIG:EDGE:SLOPE {val}')
        actual = scope.query('TRIG:EDGE:SLOPE?')
        print(f'SLOPE {val} -> {actual}')
    except Exception as e:
        print(f'SLOPE {val} -> ERROR: {e}')

# Trigger source
for val in ['CHAN1', 'CHAN2', 'EXT', 'LINE']:
    try:
        scope.write(f'TRIGGER:EDGE:SOURCE {val}')
        actual = scope.query('TRIGGER:EDGE:SOURCE?')
        print(f'SOURCE {val} -> {actual}')
    except Exception as e:
        print(f'SOURCE {val} -> ERROR: {e}')

# Trigger sweep mode
for val in ['AUTO', 'NORM', 'NORMAL', 'SING', 'SINGLE']:
    try:
        scope.write(f'TRIGGER:SWEEP {val}')
        actual = scope.query('TRIGGER:SWEEP?')
        print(f'SWEEP {val} -> {actual}')
    except Exception as e:
        print(f'SWEEP {val} -> ERROR: {e}')
```

---

## Test 10: Self-Calibration

**Goal:** Find calibration command

```python
for cmd in ['*CAL?', 'CAL:SELF?', 'CALIBRATE?', 'CALIBRATE:SELF?',
            'SELF:TEST?', '*TST?']:
    try:
        resp = scope.query(cmd)
        print(f'{cmd} -> {resp}')
    except Exception as e:
        print(f'{cmd} -> ERROR: {e}')
```

---

## Quick Test Template (Copy-Paste Ready)

If you just want to quickly test everything in one go:

```python
import pyvisa
import time

rm = pyvisa.ResourceManager()
resources = rm.list_resources()
print(f"Found: {resources}")

# Connect - replace SERIALNUM with your serial
scope = rm.open_resource(resources[0])  # or specify exact resource string
scope.timeout = 5000  # 5 second timeout

results = {}

# All commands to test
test_queries = [
    '*IDN?',
    'WAV:PRE?', 'WAV:PREAMBLE?', 'WAVEFORM:PREAMBLE?',
    'WAV:XINC?', 'WAV:YINC?', 'WAV:XORG?', 'WAV:YORG?',
    'WAV:XREF?', 'WAV:YREF?', 'WAV:POINTS?', 'WAV:FORMAT?',
    'WAV:TYPE?', 'WAV:COUNT?', 'WAV:SOUR?', 'WAV:SOURCE?',
    'CHANNEL1:PROBE?', 'CHAN1:PROB?',
    'MEAS:VPP?', 'MEAS:VRMS?', 'MEAS:FREQ?',
    '*CAL?', '*TST?',
    'SYST:ERR?', 'SYSTEM:ERROR?',
]

for cmd in test_queries:
    try:
        resp = scope.query(cmd)
        results[cmd] = resp.strip()
        print(f'OK   {cmd:35s} -> {resp.strip()}')
    except Exception as e:
        results[cmd] = f'ERROR: {e}'
        print(f'FAIL {cmd:35s} -> {e}')
    time.sleep(0.1)

# Save results
with open('scpi_test_results.txt', 'w') as f:
    for cmd, resp in results.items():
        f.write(f'{cmd}\t{resp}\n')

print(f"\nResults saved to scpi_test_results.txt")
print(f"Working: {sum(1 for v in results.values() if not v.startswith('ERROR'))}")
print(f"Failed:  {sum(1 for v in results.values() if v.startswith('ERROR'))}")

scope.close()
```

---

## Priority Order

If you have limited time, do these first:
1. **Test 1** (`*IDN?`) — quick, essential
2. **Test 2** (`WAV:PREAMBLE?`) — MOST IMPORTANT for actual use
3. **Test 3** (`WAV:SOURCE`) — needed for 2-channel support
4. **Test 4** (V/div values) — needed for scale control
5. Rest can wait

Save all Wireshark captures as `.pcapng` files in the project directory.
