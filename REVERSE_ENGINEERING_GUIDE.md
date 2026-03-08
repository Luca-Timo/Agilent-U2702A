# Reverse Engineering Guide: U2702A Protocol

> Step-by-step guide for capturing the U2702A's undocumented SCPI commands.
> Last updated: 2026-03-04

---

## Why This Is Needed

The U2702A officially only supports IVI-COM drivers (Windows). However, community members confirmed that SCPI commands are used internally. We need to capture these commands to build our macOS driver.

---

## Method 1: IO Monitor (RECOMMENDED)

This is the easiest and most reliable method. Confirmed working by Keysight community members.

### Setup

1. **Windows Environment** (VM is fine):
   - Install **Agilent/Keysight IO Libraries Suite**
     - Download: https://www.keysight.com/us/en/lib/software-detail/computer-software/io-libraries-suite-downloads-2175637.html
   - Install **Agilent Measurement Manager (AMM)**
     - Included with U2702A IVI driver package
     - Download: https://www.keysight.com/us/en/lib/software-detail/driver/u2701a-u2702a-usb-modular-oscilloscope-ivi-instrument-drivers-1540317.html
   - Connect U2702A via USB (use USB passthrough if in VM)

2. **Verify Connection**:
   - Open Keysight Connection Expert
   - Confirm U2702A appears as a USBTMC device
   - Note the VISA resource string (e.g., `USB0::0x0957::0x2918::SERIALNUM::INSTR`)

### Capture Procedure

1. **Open IO Monitor**:
   - Start Menu -> Keysight IO Libraries -> IO Monitor
   - Or: from Connection Expert toolbar

2. **Configure IO Monitor**:
   - Enable capture for the U2702A's VISA resource
   - Set to capture both sent and received data
   - Enable timestamps

3. **Systematic Capture** (perform each in order, save log after each):

   **a. Connection & Identity**
   - Open AMM
   - Let it connect to the scope
   - Note all initialization commands sent

   **b. Channel Configuration**
   - Enable CH1, disable CH2
   - Change CH1 V/div through: 5mV, 10mV, 20mV, 50mV, 100mV, 200mV, 500mV, 1V, 2V, 5V
   - Change coupling: DC -> AC -> DC
   - Change probe: 1x -> 10x -> 1x
   - Enable CH2, repeat above

   **c. Timebase**
   - Change T/div through: 5ns, 10ns, 20ns, 50ns, 100ns, 200ns, 500ns, 1us, 2us, 5us, 10us, 20us, 50us, 100us, 200us, 500us, 1ms, 2ms, 5ms, 10ms, 20ms, 50ms, 100ms, 200ms, 500ms, 1s

   **d. Trigger**
   - Set trigger source: CH1, CH2
   - Set trigger type: Edge rising, Edge falling
   - Adjust trigger level (multiple values)
   - Set trigger mode: Auto, Normal

   **e. Acquisition**
   - Click Run
   - Click Stop
   - Click Single
   - Click Auto-Set (if available)

   **f. Waveform Data**
   - With a signal connected, capture waveform
   - Note the data transfer commands and binary format

   **g. Measurements**
   - Enable each measurement type one at a time
   - Record the command for each: Vpp, Vrms, Freq, Period, Rise, Fall

   **h. Calibration**
   - If AMM has a calibration function, run it
   - Record calibration commands

4. **Save Complete Log**:
   - File -> Save As -> save as text file
   - Copy to the `docs/` folder in this project

### Expected Output Format
IO Monitor typically shows:
```
[Timestamp] WRITE: ":CHAN1:DISP ON\n"
[Timestamp] WRITE: ":CHAN1:SCAL 1.0\n"
[Timestamp] WRITE: ":WAV:SOUR CHAN1\n"
[Timestamp] WRITE: ":WAV:DATA?\n"
[Timestamp] READ:  #800001000<binary data>
```

---

## Method 2: Wireshark USB Capture

Use this if IO Monitor doesn't give clean SCPI strings, or to capture lower-level protocol details.

### Setup on Windows

1. Install **USBPcap**: https://desowin.org/usbpcap/
2. Install **Wireshark**: https://www.wireshark.org/
3. Restart after USBPcap installation

### Capture Procedure

1. Open Wireshark
2. Select the USBPcap interface corresponding to the U2702A's USB bus
3. Start capture
4. Open AMM and perform operations
5. Stop capture

### Analysis

1. Filter by U2702A endpoint:
   ```
   usb.device_address == <device_address>
   ```

2. Look for USBTMC bulk transfers:
   ```
   usb.transfer_type == 0x03
   ```

3. In packet details, expand "USB URB" and look at the data payload
4. SCPI commands will appear as ASCII strings in the payload
5. Binary waveform data will be in bulk IN transfers

### Tips
- USBTMC uses bulk endpoints for command/response
- Control endpoint (EP0) handles USB standard requests
- Bulk OUT = commands sent to scope
- Bulk IN = responses from scope
- USBTMC header is 12 bytes before the SCPI payload

---

## Method 3: IVI-COM DLL Analysis (Advanced)

### Tools Needed
- .NET decompiler (ILSpy, dnSpy, dotPeek)
- Or: Dependency Walker for native DLLs

### Approach
1. Locate IVI-COM DLLs in the installation directory:
   - Typically: `C:\Program Files\IVI Foundation\IVI\Bin\`
   - Or: `C:\Program Files (x86)\Agilent\IVI\Bin\`
2. Open DLLs in decompiler
3. Look for string constants containing SCPI commands
4. Trace the call flow from public API methods to SCPI writes

---

## Method 4: AMM Command Logger

AMM includes built-in tools:
- **Command Logger**: Logs configuration commands during operation
- **Code Converter**: Translates logged commands to VEE, VB, C++, C#

1. Open AMM
2. Tools -> Command Logger (or similar menu)
3. Perform operations
4. Export logged commands

---

## Validation: Testing Captured Commands

Once commands are captured, test them from Python:

```python
import pyvisa

# On Windows (for initial testing)
rm = pyvisa.ResourceManager()  # Uses NI-VISA
# OR on Mac:
# rm = pyvisa.ResourceManager('@py')  # Uses pyvisa-py

# Find the device
resources = rm.list_resources()
print(resources)

# Connect
scope = rm.open_resource('USB0::0x0957::0x2918::SERIALNUM::INSTR')

# Test identity
try:
    idn = scope.query('*IDN?')
    print(f"Identity: {idn}")
except Exception as e:
    print(f"*IDN? failed: {e}")

# Test a captured command
try:
    response = scope.query(':CHAN1:SCAL?')  # Example
    print(f"CH1 Scale: {response}")
except Exception as e:
    print(f"Command failed: {e}")

scope.close()
```

---

## Document Results

After capturing commands, update `SCPI_COMMANDS.md` with:
1. Exact command strings (case-sensitive)
2. Expected responses
3. Parameter ranges
4. Any initialization sequence required
5. Waveform data format details
6. Binary block header format

---

## Safety Notes

- Reverse engineering for interoperability is legal in most jurisdictions
- We are not bypassing any copy protection or DRM
- We are accessing our own hardware via standard USB protocols
- The SCPI commands are sent to hardware we own
- This is equivalent to running a logic analyzer on our own equipment
