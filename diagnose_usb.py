#!/usr/bin/env python3
"""
Low-level USB diagnostic for U2702A boot issue on macOS.

Tests every possible approach to communicate with the device.
Run with: sudo python3 diagnose_usb.py
"""

import ctypes
import ctypes.util
import os
import sys
import time

VID = 0x0957
PID_BOOT = 0x2818
PID_OPER = 0x2918

# First boot step: read 1 byte from wIndex=0x047E
STEP1 = (0xC0, 0x0C, 0x0000, 0x047E, 1)


def load_libusb():
    paths = [
        "/opt/homebrew/lib/libusb-1.0.dylib",
        "/usr/local/lib/libusb-1.0.dylib",
        ctypes.util.find_library("usb-1.0"),
    ]
    for p in paths:
        if p and os.path.exists(p):
            try:
                lib = ctypes.cdll.LoadLibrary(p)
                print(f"[+] Loaded libusb: {p}")
                return lib
            except OSError:
                continue
    raise RuntimeError("libusb not found")


def setup_signatures(lib):
    """Declare all function signatures (critical on arm64)."""
    lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_init.restype = ctypes.c_int

    lib.libusb_exit.argtypes = [ctypes.c_void_p]
    lib.libusb_exit.restype = None

    lib.libusb_open_device_with_vid_pid.argtypes = [
        ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16
    ]
    lib.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p

    lib.libusb_close.argtypes = [ctypes.c_void_p]
    lib.libusb_close.restype = None

    lib.libusb_control_transfer.argtypes = [
        ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8,
        ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p,
        ctypes.c_uint16, ctypes.c_uint,
    ]
    lib.libusb_control_transfer.restype = ctypes.c_int

    lib.libusb_set_configuration.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_set_configuration.restype = ctypes.c_int

    lib.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_claim_interface.restype = ctypes.c_int

    lib.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_release_interface.restype = ctypes.c_int

    lib.libusb_kernel_driver_active.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_kernel_driver_active.restype = ctypes.c_int

    lib.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.libusb_detach_kernel_driver.restype = ctypes.c_int

    lib.libusb_set_auto_detach_kernel_driver.argtypes = [
        ctypes.c_void_p, ctypes.c_int
    ]
    lib.libusb_set_auto_detach_kernel_driver.restype = ctypes.c_int

    lib.libusb_get_configuration.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)
    ]
    lib.libusb_get_configuration.restype = ctypes.c_int

    lib.libusb_reset_device.argtypes = [ctypes.c_void_p]
    lib.libusb_reset_device.restype = ctypes.c_int

    lib.libusb_strerror.argtypes = [ctypes.c_int]
    lib.libusb_strerror.restype = ctypes.c_char_p

    # Device descriptor
    lib.libusb_get_device.argtypes = [ctypes.c_void_p]
    lib.libusb_get_device.restype = ctypes.c_void_p

    lib.libusb_get_bus_number.argtypes = [ctypes.c_void_p]
    lib.libusb_get_bus_number.restype = ctypes.c_uint8

    lib.libusb_get_device_address.argtypes = [ctypes.c_void_p]
    lib.libusb_get_device_address.restype = ctypes.c_uint8


def strerror(lib, code):
    try:
        return lib.libusb_strerror(code).decode()
    except Exception:
        return f"error {code}"


LIBUSB_ERRORS = {
    0: "SUCCESS",
    -1: "ERROR_IO",
    -2: "ERROR_INVALID_PARAM",
    -3: "ERROR_ACCESS",
    -4: "ERROR_NO_DEVICE",
    -5: "ERROR_NOT_FOUND",
    -6: "ERROR_BUSY",
    -7: "ERROR_TIMEOUT",
    -8: "ERROR_OVERFLOW",
    -9: "ERROR_PIPE",
    -10: "ERROR_INTERRUPTED",
    -11: "ERROR_NO_MEM",
    -12: "ERROR_NOT_SUPPORTED",
    -99: "ERROR_OTHER",
}


def err_name(code):
    return LIBUSB_ERRORS.get(code, f"UNKNOWN({code})")


def try_control_transfer(lib, handle, timeout_ms, label=""):
    """Try the first boot step control transfer."""
    bmReq, bReq, wVal, wIdx, wLen = STEP1
    buf = (ctypes.c_uint8 * wLen)()
    ret = lib.libusb_control_transfer(
        handle, bmReq, bReq, wVal, wIdx, buf, wLen, timeout_ms
    )
    if ret >= 0:
        data = bytes(buf[:ret])
        print(f"  [+] {label}Control transfer SUCCESS! Got {ret} bytes: {data.hex()}")
        return True
    else:
        print(f"  [-] {label}Control transfer failed: {err_name(ret)} ({ret})")
        return False


def main():
    print("=" * 60)
    print("U2702A USB Diagnostic")
    print("=" * 60)
    print(f"  Running as: uid={os.getuid()} ({'root' if os.getuid() == 0 else 'user'})")
    print(f"  Python: {sys.executable}")
    print()

    lib = load_libusb()
    setup_signatures(lib)

    ctx = ctypes.c_void_p()
    ret = lib.libusb_init(ctypes.byref(ctx))
    if ret != 0:
        print(f"[-] libusb_init failed: {err_name(ret)}")
        return
    print("[+] libusb initialized")

    # Try to open the device
    for pid, name in [(PID_BOOT, "boot"), (PID_OPER, "operational")]:
        handle = lib.libusb_open_device_with_vid_pid(ctx, VID, pid)
        if handle:
            print(f"[+] Opened {name} device (PID 0x{pid:04X})")
            break
    else:
        print("[-] Cannot open device with either PID")
        lib.libusb_exit(ctx)
        return

    # Get bus/address info
    dev = lib.libusb_get_device(handle)
    if dev:
        bus = lib.libusb_get_bus_number(dev)
        addr = lib.libusb_get_device_address(dev)
        print(f"    Bus {bus}, Address {addr}")

    # Check current configuration
    config = ctypes.c_int(-1)
    ret = lib.libusb_get_configuration(handle, ctypes.byref(config))
    print(f"[*] Current configuration: {config.value} (ret={err_name(ret)})")

    # Check kernel driver
    for iface in range(4):
        ret = lib.libusb_kernel_driver_active(handle, iface)
        if ret == 1:
            print(f"[!] Kernel driver active on interface {iface}")
        elif ret == 0:
            pass  # No driver
        else:
            if iface == 0:
                print(f"[*] Kernel driver check iface 0: {err_name(ret)}")

    print()
    print("--- Test 1: Direct control transfer (no setup, 2s timeout) ---")
    try_control_transfer(lib, handle, 2000, "")

    print()
    print("--- Test 2: Auto-detach kernel driver, then transfer ---")
    ret = lib.libusb_set_auto_detach_kernel_driver(handle, 1)
    print(f"  Auto-detach: {err_name(ret)}")
    try_control_transfer(lib, handle, 2000, "")

    print()
    print("--- Test 3: Detach kernel driver on iface 0, then transfer ---")
    ret = lib.libusb_detach_kernel_driver(handle, 0)
    print(f"  Detach iface 0: {err_name(ret)}")
    try_control_transfer(lib, handle, 2000, "")

    print()
    print("--- Test 4: Set configuration 1, then transfer ---")
    ret = lib.libusb_set_configuration(handle, 1)
    print(f"  Set config 1: {err_name(ret)}")
    if ret == 0:
        try_control_transfer(lib, handle, 2000, "")

    print()
    print("--- Test 5: Claim interface 0, then transfer ---")
    ret = lib.libusb_claim_interface(handle, 0)
    print(f"  Claim iface 0: {err_name(ret)}")
    if ret == 0:
        try_control_transfer(lib, handle, 2000, "")
        lib.libusb_release_interface(handle, 0)

    print()
    print("--- Test 6: Reset device, reopen, then transfer ---")
    ret = lib.libusb_reset_device(handle)
    print(f"  Reset device: {err_name(ret)}")
    if ret == 0:
        try_control_transfer(lib, handle, 2000, "after reset: ")
    elif ret == -4:  # NO_DEVICE — device re-enumerated
        print("  Device re-enumerated after reset, reopening...")
        lib.libusb_close(handle)
        time.sleep(2)
        handle = lib.libusb_open_device_with_vid_pid(ctx, VID, PID_BOOT)
        if not handle:
            handle = lib.libusb_open_device_with_vid_pid(ctx, VID, PID_OPER)
        if handle:
            print("  [+] Reopened device")
            try_control_transfer(lib, handle, 2000, "after reopen: ")
        else:
            print("  [-] Could not reopen device")
            lib.libusb_exit(ctx)
            return

    print()
    print("--- Test 7: Set config 0 (unconfigure), set config 1, transfer ---")
    ret = lib.libusb_set_configuration(handle, 0)
    print(f"  Set config 0: {err_name(ret)}")
    ret = lib.libusb_set_configuration(handle, 1)
    print(f"  Set config 1: {err_name(ret)}")
    if ret == 0:
        try_control_transfer(lib, handle, 2000, "")

    print()
    print("--- Test 8: Control transfer with longer timeout (10s) ---")
    try_control_transfer(lib, handle, 10000, "10s timeout: ")

    # Cleanup
    lib.libusb_close(handle)
    lib.libusb_exit(ctx)
    print()
    print("Done.")


if __name__ == "__main__":
    main()
