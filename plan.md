# ESP32-S3 USB Bridge Firmware — Implementation Plan

## Overview

Create a PlatformIO project at `firmware/` that builds an ESP32-S3 firmware which:
1. Acts as USB Host to the U2702A oscilloscope (native USB OTG port)
2. Sends the 6-step boot sequence (vendor control transfers) on device plug-in
3. Proxies SCPI commands between the Mac (via UART/CP2102N) and the U2702A (via USBTMC bulk transfers)

```
Mac ←── USB-UART (CP2102N, 2Mbps) ──→ ESP32-S3 ←── USB OTG Host ──→ U2702A
         pyserial                      firmware                       USBTMC
```

## Project Structure

```
firmware/
├── platformio.ini              # PIO config: esp32-s3-devkitc-1, ESP-IDF framework
├── sdkconfig.defaults          # Enable USB Host, set stack sizes
├── src/
│   ├── main.c                  # App entry: init tasks, event loop
│   ├── usb_host.c/.h           # USB Host: device detection, open, control transfers
│   ├── u2702a_boot.c/.h        # Boot sequence: 6 vendor control transfers
│   ├── usbtmc.c/.h             # USBTMC protocol: bulk msg framing (DEV_DEP_MSG_OUT/IN)
│   ├── serial_bridge.c/.h      # UART: receive SCPI from Mac, forward to USBTMC, return responses
│   └── led.c/.h                # Status LED (GPIO48 on DevKitC-1 = addressable RGB)
└── README.md                   # Wiring, flashing, usage instructions
```

## Files to Create

### 1. `firmware/platformio.ini`
- Platform: `espressif32`
- Board: `esp32-s3-devkitc-1`
- Framework: `espidf`
- Monitor speed: 2000000 (2 Mbps for CP2102N)
- Build flags for USB Host enable

### 2. `firmware/sdkconfig.defaults`
- `CONFIG_USB_OTG_SUPPORTED=y`
- `CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE=1024`
- `CONFIG_USB_HOST_HW_BUFFER_BIAS_BALANCED=y`
- UART/serial config for 2Mbps

### 3. `firmware/src/main.c`
- Initialize NVS, UART, LED
- Start USB Host library task (`usb_host_install`)
- Start USB Host client task (device detection + event loop)
- Start serial bridge task (reads UART, dispatches to USBTMC)
- State machine: IDLE → DEVICE_CONNECTED → BOOTING → OPERATIONAL → READY

### 4. `firmware/src/usb_host.c/.h`
- `usb_host_task()` — calls `usb_host_lib_handle_events()` in a loop
- `usb_client_task()` — registers client, handles CONNECT/DISCONNECT events
- On device connect: check VID=0x0957, PID=0x2818 or 0x2918
  - If PID 0x2818 (boot mode): trigger boot sequence
  - If PID 0x2918 (operational): claim USBTMC interface, extract bulk endpoints
- `open_device()` — open device, get config descriptor, find interfaces/endpoints
- `close_device()` — release interface, close device

### 5. `firmware/src/u2702a_boot.c/.h`
- `u2702a_boot()` — sends the 6 vendor control transfers:
  ```
  Step 1: bmReq=0xC0 bReq=0x0C wVal=0x0000 wIdx=0x047E READ  1 byte
  Step 2: bmReq=0xC0 bReq=0x0C wVal=0x0000 wIdx=0x047D READ  6 bytes
  Step 3: bmReq=0xC0 bReq=0x0C wVal=0x0000 wIdx=0x0484 READ  5 bytes
  Step 4: bmReq=0xC0 bReq=0x0C wVal=0x0000 wIdx=0x0472 READ 12 bytes
  Step 5: bmReq=0xC0 bReq=0x0C wVal=0x0000 wIdx=0x047A READ  1 byte
  Step 6: bmReq=0x40 bReq=0x0C wVal=0x0000 wIdx=0x0475 WRITE 8 bytes
          Data: 00 00 01 01 00 00 08 01
  ```
- Uses `usb_host_transfer_submit_control()` with 8-byte setup packet
- After boot: close device, wait for re-enumeration as PID 0x2918

### 6. `firmware/src/usbtmc.c/.h`
- USBTMC message framing per USB TMC spec:
  - **DEV_DEP_MSG_OUT** (MsgID=1): 12-byte header + SCPI command, padded to 4-byte boundary
  - **REQUEST_DEV_DEP_MSG_IN** (MsgID=2): 12-byte header requesting N bytes
  - **DEV_DEP_MSG_IN** (MsgID=2): 12-byte header + response data from bulk-IN
- `usbtmc_write(cmd, len)` — build MSG_OUT, submit bulk-OUT transfer
- `usbtmc_read(buf, max_len)` — send REQUEST_MSG_IN, then read bulk-IN
- `usbtmc_query(cmd, response_buf, max_len)` — write + read (most SCPI queries)
- bTag counter: increment 1-255, wrapping (skip 0)
- Bulk endpoint addresses: typically EP1 OUT (0x01), EP2 IN (0x82) — extracted from config descriptor

### 7. `firmware/src/serial_bridge.c/.h`
- Simple line-based protocol over UART at 2 Mbps:
  - **Text commands** (Mac → ESP32): SCPI command terminated by `\n`
  - **Text responses** (ESP32 → Mac): SCPI response terminated by `\n`
  - **Binary data** (ESP32 → Mac): for WAV:DATA? responses
    - Prefix: `#` + 4-byte little-endian length
    - Payload: raw bytes (stripped of USBTMC framing and IEEE 488.2 header)
  - **Status messages**: `!STATUS:<state>\n` (BOOTING, READY, DISCONNECTED, ERROR)
- UART RX task: read lines, dispatch to `usbtmc_query()` or `usbtmc_write()`
- UART TX: send responses back

### 8. `firmware/src/led.c/.h`
- RGB LED on GPIO48 (WS2812/addressable LED on DevKitC-1)
- States: Red=no device, Yellow=booting, Green=ready, Blue=data transfer

## Key Design Decisions

1. **ESP-IDF framework** (not Arduino) — full USB Host API access, proper FreeRTOS tasks
2. **2 Mbps UART** — CP2102N supports up to 3 Mbps, 2 Mbps is reliable
3. **Strip zero-padding on ESP32** — only forward 1256 active ADC bytes per channel
4. **Simple text protocol** over serial — easy to integrate with Python `pyserial`
5. **3 FreeRTOS tasks**: USB Host library daemon, USB client (boot + USBTMC), serial bridge

## Build & Flash

```bash
cd firmware
pio run                          # Build
pio run -t upload                # Flash via USB-UART port
pio device monitor -b 2000000    # Serial monitor at 2Mbps
```

## .gitignore additions

```
firmware/.pio/
firmware/.vscode/
```
