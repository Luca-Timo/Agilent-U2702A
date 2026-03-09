#!/usr/bin/env python3
"""
U2702A USB Diagnostic Level 3 — USB reset + immediate boot.

Theory: The device needs a USB reset before it'll respond to control
transfers. On Windows the driver does this automatically.

Run with: sudo python3 diagnose_usb3.py
"""

import ctypes
import ctypes.util
import os
import sys
import time

VID = 0x0957
PID_BOOT = 0x2818
PID_OPER = 0x2918

BOOT_SEQUENCE = [
    (0xC0, 0x0C, 0x0000, 0x047E, 1),
    (0xC0, 0x0C, 0x0000, 0x047D, 6),
    (0xC0, 0x0C, 0x0000, 0x0484, 5),
    (0xC0, 0x0C, 0x0000, 0x0472, 12),
    (0xC0, 0x0C, 0x0000, 0x047A, 1),
    (0x40, 0x0C, 0x0000, 0x0475,
     bytes([0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x08, 0x01])),
]

ERRORS = {
    0: "SUCCESS", -1: "IO", -2: "INVALID_PARAM", -3: "ACCESS",
    -4: "NO_DEVICE", -5: "NOT_FOUND", -6: "BUSY", -7: "TIMEOUT",
    -8: "OVERFLOW", -9: "PIPE", -10: "INTERRUPTED", -99: "OTHER",
}


def err(code):
    return ERRORS.get(code, f"?({code})")


def load_libusb():
    for p in ["/opt/homebrew/lib/libusb-1.0.dylib",
              "/usr/local/lib/libusb-1.0.dylib"]:
        if os.path.exists(p):
            lib = ctypes.cdll.LoadLibrary(p)
            # All signatures (arm64-safe)
            for name, at, rt in [
                ("libusb_init", [ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int),
                ("libusb_exit", [ctypes.c_void_p], None),
                ("libusb_open_device_with_vid_pid",
                 [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16], ctypes.c_void_p),
                ("libusb_close", [ctypes.c_void_p], None),
                ("libusb_control_transfer",
                 [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8,
                  ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p,
                  ctypes.c_uint16, ctypes.c_uint], ctypes.c_int),
                ("libusb_reset_device", [ctypes.c_void_p], ctypes.c_int),
                ("libusb_clear_halt", [ctypes.c_void_p, ctypes.c_uint8], ctypes.c_int),
                ("libusb_set_auto_detach_kernel_driver",
                 [ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            ]:
                fn = getattr(lib, name)
                fn.argtypes = at
                fn.restype = rt
            return lib
    raise RuntimeError("libusb not found")


def open_device(lib, ctx):
    """Open the boot or operational device."""
    h = lib.libusb_open_device_with_vid_pid(ctx, VID, PID_BOOT)
    if h:
        return h, PID_BOOT
    h = lib.libusb_open_device_with_vid_pid(ctx, VID, PID_OPER)
    if h:
        return h, PID_OPER
    return None, None


def try_boot_step(lib, handle, step_num, transfer, timeout=2000):
    """Try one boot step. Returns True on success."""
    if isinstance(transfer[4], int):
        bmReq, bReq, wVal, wIdx, wLen = transfer
        buf = (ctypes.c_uint8 * wLen)()
        ret = lib.libusb_control_transfer(
            handle, bmReq, bReq, wVal, wIdx, buf, wLen, timeout)
        if ret >= 0:
            print(f"    Step {step_num}: READ  wIdx=0x{wIdx:04X} -> {bytes(buf[:ret]).hex()}")
            return True
        else:
            print(f"    Step {step_num}: READ  wIdx=0x{wIdx:04X} -> {err(ret)}")
            return False
    else:
        bmReq, bReq, wVal, wIdx, data = transfer
        buf = (ctypes.c_uint8 * len(data))(*data)
        ret = lib.libusb_control_transfer(
            handle, bmReq, bReq, wVal, wIdx, buf, len(data), timeout)
        if ret >= 0:
            print(f"    Step {step_num}: WRITE wIdx=0x{wIdx:04X} -> OK ({ret} bytes)")
            return True
        else:
            print(f"    Step {step_num}: WRITE wIdx=0x{wIdx:04X} -> {err(ret)}")
            return False


def main():
    print("=" * 60)
    print("U2702A USB Diagnostic — Level 3 (Reset + Boot)")
    print("=" * 60)
    print(f"  uid={os.getuid()} ({'root' if os.getuid() == 0 else 'user'})")
    print()

    lib = load_libusb()
    ctx = ctypes.c_void_p()
    lib.libusb_init(ctypes.byref(ctx))

    handle, pid = open_device(lib, ctx)
    if not handle:
        print("[-] No device found")
        lib.libusb_exit(ctx)
        return
    print(f"[+] Opened device PID 0x{pid:04X}")

    # ============================================================
    # Test A: USB reset, then immediately try boot sequence
    # ============================================================
    print()
    print("=== Test A: USB reset, reopen, boot sequence ===")
    print()

    lib.libusb_set_auto_detach_kernel_driver(handle, 1)

    print("  Sending USB reset...")
    ret = lib.libusb_reset_device(handle)
    print(f"  Reset result: {err(ret)}")

    if ret == -4:  # NO_DEVICE — device re-enumerated with new address
        print("  Device re-enumerated, closing old handle...")
        lib.libusb_close(handle)
        # Need fresh context after re-enumeration
        lib.libusb_exit(ctx)
        time.sleep(1.0)
        ctx = ctypes.c_void_p()
        lib.libusb_init(ctypes.byref(ctx))
        print("  Waiting 1s, then reopening...")
        handle, pid = open_device(lib, ctx)
        if not handle:
            print("  [-] Cannot reopen after reset, trying longer wait...")
            for wait in [2, 3, 5]:
                time.sleep(wait)
                handle, pid = open_device(lib, ctx)
                if handle:
                    break
        if not handle:
            print("  [-] Device not found after reset")
            lib.libusb_exit(ctx)
            return
        print(f"  [+] Reopened device PID 0x{pid:04X}")

    if pid == PID_OPER:
        print("  [!] Device is already operational after reset!")
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)
        return

    print()
    print("  Attempting boot sequence (2s timeout per step):")
    all_ok = True
    for i, transfer in enumerate(BOOT_SEQUENCE):
        if not try_boot_step(lib, handle, i + 1, transfer):
            all_ok = False
            break

    if all_ok:
        print()
        print("  [+] Boot sequence sent! Polling for operational device...")
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)
        for attempt in range(40):
            time.sleep(0.5)
            ctx2 = ctypes.c_void_p()
            lib.libusb_init(ctypes.byref(ctx2))
            h2 = lib.libusb_open_device_with_vid_pid(ctx2, VID, PID_OPER)
            if h2:
                print(f"  [+] Device operational after {(attempt+1)*0.5:.1f}s!")
                lib.libusb_close(h2)
                lib.libusb_exit(ctx2)
                return
            lib.libusb_exit(ctx2)
        print("  [-] Timeout waiting for operational device")
        return

    # ============================================================
    # Test B: Clear halt on EP0, then try
    # ============================================================
    print()
    print("=== Test B: Clear halt on EP0 ===")
    print()

    ret = lib.libusb_clear_halt(handle, 0x00)
    print(f"  Clear halt EP 0x00: {err(ret)}")
    ret = lib.libusb_clear_halt(handle, 0x80)
    print(f"  Clear halt EP 0x80: {err(ret)}")

    print("  Trying boot step 1:")
    try_boot_step(lib, handle, 1, BOOT_SEQUENCE[0])

    # ============================================================
    # Test C: Rapid reset + transfer (minimize time between reset and transfer)
    # ============================================================
    print()
    print("=== Test C: Rapid reset + immediate transfer ===")
    print()

    # Close and reopen fresh
    lib.libusb_close(handle)
    lib.libusb_exit(ctx)
    ctx = ctypes.c_void_p()
    lib.libusb_init(ctypes.byref(ctx))
    handle, pid = open_device(lib, ctx)
    if not handle:
        print("  [-] Cannot reopen")
        lib.libusb_exit(ctx)
        return

    print("  Reset + immediate transfer (no delay)...")
    ret = lib.libusb_reset_device(handle)
    print(f"  Reset: {err(ret)}")

    if ret == 0:
        # Device stayed at same address — try immediately
        print("  Trying boot step 1 immediately after reset:")
        try_boot_step(lib, handle, 1, BOOT_SEQUENCE[0], timeout=5000)
    elif ret == -4:
        # Re-enumerated — try different delays
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)
        for delay in [0.1, 0.3, 0.5, 1.0, 2.0]:
            print(f"  Waiting {delay}s after re-enumeration...")
            time.sleep(delay)
            ctx = ctypes.c_void_p()
            lib.libusb_init(ctypes.byref(ctx))
            handle, pid = open_device(lib, ctx)
            if handle:
                print(f"  Opened PID 0x{pid:04X}, trying boot step 1:")
                ok = try_boot_step(lib, handle, 1, BOOT_SEQUENCE[0], timeout=5000)
                lib.libusb_close(handle)
                lib.libusb_exit(ctx)
                if ok:
                    print(f"  [+] SUCCESS at delay={delay}s!")
                    return
            else:
                print(f"  Device not ready yet at {delay}s")
                lib.libusb_exit(ctx)
    else:
        lib.libusb_close(handle)
        lib.libusb_exit(ctx)

    print()
    print("All tests completed.")


if __name__ == "__main__":
    main()
