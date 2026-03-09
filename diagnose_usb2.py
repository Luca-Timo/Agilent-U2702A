#!/usr/bin/env python3
"""
U2702A USB Diagnostic Level 2 — Device descriptor & standard requests.

Checks whether the device responds to ANY USB request, not just vendor ones.
Run with: sudo python3 diagnose_usb2.py
"""

import ctypes
import ctypes.util
import os
import struct
import sys
import time

VID = 0x0957
PID_BOOT = 0x2818
PID_OPER = 0x2918

# Standard USB request types
GET_STATUS = 0x00
GET_DESCRIPTOR = 0x06
DEVICE_DESC = 0x0100
CONFIG_DESC = 0x0200
STRING_DESC = 0x0300


def load_libusb():
    paths = [
        "/opt/homebrew/lib/libusb-1.0.dylib",
        "/usr/local/lib/libusb-1.0.dylib",
    ]
    for p in paths:
        if p and os.path.exists(p):
            lib = ctypes.cdll.LoadLibrary(p)
            # Signatures
            lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
            lib.libusb_init.restype = ctypes.c_int
            lib.libusb_exit.argtypes = [ctypes.c_void_p]
            lib.libusb_exit.restype = None
            lib.libusb_open_device_with_vid_pid.argtypes = [
                ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
            lib.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
            lib.libusb_close.argtypes = [ctypes.c_void_p]
            lib.libusb_close.restype = None
            lib.libusb_control_transfer.argtypes = [
                ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8,
                ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p,
                ctypes.c_uint16, ctypes.c_uint,
            ]
            lib.libusb_control_transfer.restype = ctypes.c_int
            lib.libusb_get_device.argtypes = [ctypes.c_void_p]
            lib.libusb_get_device.restype = ctypes.c_void_p
            lib.libusb_get_device_descriptor = lib.libusb_get_device_descriptor
            return lib
    raise RuntimeError("libusb not found")


ERRORS = {
    0: "SUCCESS", -1: "IO", -2: "INVALID_PARAM", -3: "ACCESS",
    -4: "NO_DEVICE", -5: "NOT_FOUND", -6: "BUSY", -7: "TIMEOUT",
    -8: "OVERFLOW", -9: "PIPE", -10: "INTERRUPTED", -11: "NO_MEM",
    -12: "NOT_SUPPORTED", -99: "OTHER",
}


def ctrl(lib, handle, bmReq, bReq, wVal, wIdx, wLen, timeout=2000):
    """Do a control transfer, return (ret_code, data_bytes)."""
    buf = (ctypes.c_uint8 * max(wLen, 64))()
    ret = lib.libusb_control_transfer(
        handle, bmReq, bReq, wVal, wIdx, buf, wLen, timeout
    )
    return ret, bytes(buf[:max(0, ret)])


def main():
    print("=" * 60)
    print("U2702A USB Diagnostic — Level 2")
    print("=" * 60)
    print(f"  uid={os.getuid()} ({'root' if os.getuid() == 0 else 'user'})")
    print()

    lib = load_libusb()
    ctx = ctypes.c_void_p()
    lib.libusb_init(ctypes.byref(ctx))

    handle = lib.libusb_open_device_with_vid_pid(ctx, VID, PID_BOOT)
    if not handle:
        handle = lib.libusb_open_device_with_vid_pid(ctx, VID, PID_OPER)
        if not handle:
            print("[-] No device found")
            lib.libusb_exit(ctx)
            return
        print(f"[+] Opened operational device (0x{PID_OPER:04X})")
    else:
        print(f"[+] Opened boot device (0x{PID_BOOT:04X})")

    # Test 1: GET_STATUS (simplest possible standard request)
    print()
    print("--- Standard USB requests (2s timeout) ---")
    print()

    print("  GET_STATUS (device):")
    ret, data = ctrl(lib, handle, 0x80, GET_STATUS, 0, 0, 2)
    if ret >= 0:
        print(f"    [+] OK: {data.hex()} ({ret} bytes)")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    print()
    print("  GET_DESCRIPTOR (device descriptor):")
    ret, data = ctrl(lib, handle, 0x80, GET_DESCRIPTOR, DEVICE_DESC, 0, 18)
    if ret >= 0:
        print(f"    [+] OK: {data.hex()} ({ret} bytes)")
        if ret >= 18:
            vid = struct.unpack_from('<H', data, 8)[0]
            pid = struct.unpack_from('<H', data, 10)[0]
            bcd = struct.unpack_from('<H', data, 12)[0]
            ncfg = data[17]
            print(f"    VID=0x{vid:04X} PID=0x{pid:04X} bcdDevice=0x{bcd:04X} nConfigs={ncfg}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    print()
    print("  GET_DESCRIPTOR (config descriptor):")
    ret, data = ctrl(lib, handle, 0x80, GET_DESCRIPTOR, CONFIG_DESC, 0, 64)
    if ret >= 0:
        print(f"    [+] OK: {data.hex()} ({ret} bytes)")
        if ret >= 4:
            total_len = struct.unpack_from('<H', data, 2)[0]
            num_ifaces = data[4] if ret >= 5 else '?'
            config_val = data[5] if ret >= 6 else '?'
            print(f"    Total length={total_len}, interfaces={num_ifaces}, configValue={config_val}")
            # Parse interface descriptors
            offset = 9  # skip config descriptor
            while offset + 9 <= ret:
                blen = data[offset]
                btype = data[offset + 1]
                if btype == 4:  # Interface descriptor
                    iface_num = data[offset + 2]
                    iface_class = data[offset + 5]
                    iface_subclass = data[offset + 6]
                    iface_proto = data[offset + 7]
                    print(f"    Interface {iface_num}: class=0x{iface_class:02X} "
                          f"subclass=0x{iface_subclass:02X} proto=0x{iface_proto:02X}")
                elif btype == 5:  # Endpoint descriptor
                    ep_addr = data[offset + 2]
                    ep_attr = data[offset + 3]
                    ep_dir = "IN" if ep_addr & 0x80 else "OUT"
                    print(f"    Endpoint 0x{ep_addr:02X} ({ep_dir}), "
                          f"type={['ctrl','iso','bulk','intr'][ep_attr & 3]}")
                if blen == 0:
                    break
                offset += blen
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    print()
    print("  GET_DESCRIPTOR (string 1 = manufacturer):")
    ret, data = ctrl(lib, handle, 0x80, GET_DESCRIPTOR, STRING_DESC | 1, 0x0409, 64)
    if ret >= 0:
        try:
            s = data[2:ret].decode('utf-16-le')
            print(f"    [+] \"{s}\"")
        except Exception:
            print(f"    [+] raw: {data.hex()}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    print()
    print("  GET_DESCRIPTOR (string 2 = product):")
    ret, data = ctrl(lib, handle, 0x80, GET_DESCRIPTOR, STRING_DESC | 2, 0x0409, 64)
    if ret >= 0:
        try:
            s = data[2:ret].decode('utf-16-le')
            print(f"    [+] \"{s}\"")
        except Exception:
            print(f"    [+] raw: {data.hex()}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    print()
    print("  GET_DESCRIPTOR (string 3 = serial):")
    ret, data = ctrl(lib, handle, 0x80, GET_DESCRIPTOR, STRING_DESC | 3, 0x0409, 64)
    if ret >= 0:
        try:
            s = data[2:ret].decode('utf-16-le')
            print(f"    [+] \"{s}\"")
        except Exception:
            print(f"    [+] raw: {data.hex()}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    # Test 2: Vendor requests with different approaches
    print()
    print("--- Vendor control requests ---")
    print()

    # Original boot step 1
    print("  Vendor READ 0x0C, wIndex=0x047E (boot step 1):")
    ret, data = ctrl(lib, handle, 0xC0, 0x0C, 0x0000, 0x047E, 1)
    if ret >= 0:
        print(f"    [+] OK: {data.hex()}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    # Try bRequest 0x00 (some devices use this)
    print()
    print("  Vendor READ 0x00, wIndex=0x0000:")
    ret, data = ctrl(lib, handle, 0xC0, 0x00, 0x0000, 0x0000, 1)
    if ret >= 0:
        print(f"    [+] OK: {data.hex()}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    # Try bRequest 0x01 (common vendor request)
    print()
    print("  Vendor READ 0x01, wIndex=0x0000:")
    ret, data = ctrl(lib, handle, 0xC0, 0x01, 0x0000, 0x0000, 1)
    if ret >= 0:
        print(f"    [+] OK: {data.hex()}")
    else:
        print(f"    [-] Failed: {ERRORS.get(ret, ret)}")

    # Cleanup
    lib.libusb_close(handle)
    lib.libusb_exit(ctx)
    print()
    print("Done.")


if __name__ == "__main__":
    main()
