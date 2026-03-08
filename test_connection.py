#!/usr/bin/env python3
"""
U2702A Connection Test Script

Tests the full connection pipeline:
1. USB device detection
2. Firmware boot (if needed)
3. VISA session
4. *IDN? query
5. Initialization sequence
6. Single acquisition

Usage:
    python test_connection.py
    python test_connection.py -v          # verbose (debug logging)
    python test_connection.py --scan-only # just scan USB, don't connect
"""

import argparse
import logging
import sys
import struct

import usb.core

from instrument.boot import (
    VID_AGILENT, PID_BOOT, PID_OPERATIONAL, find_device, get_serial,
)
from instrument.connection import ConnectionManager
from instrument import protocol


def scan_usb():
    """Scan for Agilent/Keysight USB devices."""
    print("=" * 60)
    print("USB Device Scan")
    print("=" * 60)

    # Check for boot-mode device
    dev_boot = find_device(VID_AGILENT, PID_BOOT)
    if dev_boot:
        serial = get_serial(dev_boot)
        print(f"  FOUND: Boot mode device (PID 0x{PID_BOOT:04X})")
        print(f"         Serial: {serial}")
        print(f"         -> Needs firmware boot sequence")
        usb.util.dispose_resources(dev_boot)
    else:
        print(f"  No boot-mode device (PID 0x{PID_BOOT:04X})")

    # Check for operational device
    dev_op = find_device(VID_AGILENT, PID_OPERATIONAL)
    if dev_op:
        serial = get_serial(dev_op)
        print(f"  FOUND: Operational device (PID 0x{PID_OPERATIONAL:04X})")
        print(f"         Serial: {serial}")
        print(f"         -> Ready for VISA connection")
        usb.util.dispose_resources(dev_op)
    else:
        print(f"  No operational device (PID 0x{PID_OPERATIONAL:04X})")

    if not dev_boot and not dev_op:
        print()
        print("  No Agilent U2702A found!")
        print(f"  Expected VID=0x{VID_AGILENT:04X}")
        print("  Check USB cable and try again.")

    # List all Agilent USB devices
    print()
    print("All Agilent USB devices:")
    devices = list(usb.core.find(find_all=True, idVendor=VID_AGILENT))
    if devices:
        for dev in devices:
            serial = get_serial(dev) or "unknown"
            print(
                f"  VID=0x{dev.idVendor:04X} PID=0x{dev.idProduct:04X} "
                f"Serial={serial}"
            )
            usb.util.dispose_resources(dev)
    else:
        print("  (none)")

    print("=" * 60)


def test_init_sequence(mgr):
    """Run the AMM initialization sequence and report device state."""
    print()
    print("-" * 60)
    print("Running initialization sequence...")
    print("-" * 60)

    state = {}
    for cmd in protocol.INIT_SEQUENCE:
        try:
            if cmd.endswith("?"):
                response = mgr.query(cmd)
                state[cmd] = response
                print(f"  {cmd:40s} -> {response}")
            else:
                mgr.write(cmd)
                print(f"  {cmd:40s}    (sent)")
        except Exception as e:
            print(f"  {cmd:40s} -> ERROR: {e}")

    return state


def test_single_acquisition(mgr):
    """Test a single acquisition and show raw data info."""
    print()
    print("-" * 60)
    print("Testing single acquisition...")
    print("-" * 60)

    # Enable CH1
    mgr.write(protocol.channel_display_set(1, True))
    print("  CHANNEL1:DISPLAY ON")

    # Select CH1 as waveform source
    mgr.write(protocol.wav_source_set(1))
    print("  WAV:SOUR CHAN1")

    # Trigger single acquisition
    mgr.write(protocol.SINGLE)
    print("  :SINGLE")

    # Poll for data
    import time
    for attempt in range(20):
        raw = mgr.query_binary(protocol.WAV_DATA)

        if len(raw) < 12:
            print(f"  WAV:DATA? -> {len(raw)} bytes (polling...)")
            time.sleep(0.1)
            continue

        # Parse IEEE 488.2 header
        if raw[0:1] == b'#':
            n_digits = int(raw[1:2])
            byte_count = int(raw[2:2 + n_digits])
            payload = raw[2 + n_digits:]

            print(f"  WAV:DATA? -> #{n_digits}{byte_count:0{n_digits}d}")
            print(f"    Payload: {len(payload)} bytes")

            if byte_count > 2:
                prefix = payload[:2]
                adc_data = payload[2:2 + 1256]  # First half = channel data
                padding = payload[1258:]          # Second half = zeros

                print(f"    Prefix bytes: 0x{prefix[0]:02X} 0x{prefix[1]:02X}")
                print(f"    ADC data: {len(adc_data)} points")

                if len(adc_data) > 0:
                    import numpy as np
                    adc = np.frombuffer(adc_data, dtype=np.uint8)
                    print(f"    ADC min={adc.min()}, max={adc.max()}, "
                          f"mean={adc.mean():.1f}, std={adc.std():.1f}")

                    # Check if padding is all zeros
                    if len(padding) > 0:
                        pad_arr = np.frombuffer(padding, dtype=np.uint8)
                        n_nonzero = np.count_nonzero(pad_arr)
                        print(f"    Padding: {len(padding)} bytes, "
                              f"{n_nonzero} non-zero")

                print()
                print("  Single acquisition: OK!")
                return True
        else:
            # Might be the "00" polling response
            print(f"  WAV:DATA? -> {len(raw)} bytes (waiting...)")
            time.sleep(0.1)

    print("  Single acquisition: TIMEOUT (no data after 20 attempts)")
    return False


def main():
    parser = argparse.ArgumentParser(description="U2702A connection test")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--scan-only", action="store_true",
        help="Only scan for USB devices, don't connect",
    )
    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Step 1: USB scan
    scan_usb()

    if args.scan_only:
        return

    # Step 2: Connect
    print()
    print("=" * 60)
    print("Connecting...")
    print("=" * 60)

    mgr = ConnectionManager()
    try:
        mgr.connect()
        print(f"  Identity: {mgr.idn}")
        print(f"  Resource: {mgr.resource_name}")
        print(f"  Serial:   {mgr.serial}")
        print()
        print("  CONNECTION: OK!")

        # Step 3: Init sequence
        state = test_init_sequence(mgr)

        # Step 4: Single acquisition
        test_single_acquisition(mgr)

    except PermissionError as e:
        print(f"\n  PERMISSION ERROR:\n{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  FAILED: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        mgr.disconnect()
        print()
        print("Disconnected.")


if __name__ == "__main__":
    main()
