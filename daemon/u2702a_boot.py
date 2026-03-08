#!/usr/bin/env python3
"""
U2702A USB Boot Daemon

Standalone script that boots the U2702A from firmware-update mode
(PID 0x2818) to operational USBTMC mode (PID 0x2918).

Uses ctypes + libusb directly — NO Python package dependencies.
Designed to run as a macOS launchd daemon with root privileges.

Install via: sudo python3 daemon/install_daemon.py
"""

import ctypes
import ctypes.util
import os
import struct
import sys
import time
import syslog

# --- Constants ---

VID_AGILENT = 0x0957
PID_BOOT = 0x2818
PID_OPERATIONAL = 0x2918

# Boot sequence: 6 vendor-specific USB control transfers
BOOT_SEQUENCE = [
    # (bmRequestType, bRequest, wValue, wIndex, data_or_length)
    (0xC0, 0x0C, 0x0000, 0x047E, 1),      # Read 1 byte
    (0xC0, 0x0C, 0x0000, 0x047D, 6),      # Read 6 bytes
    (0xC0, 0x0C, 0x0000, 0x0484, 5),      # Read 5 bytes (U2701A/U2702A)
    (0xC0, 0x0C, 0x0000, 0x0472, 12),     # Read 12 bytes
    (0xC0, 0x0C, 0x0000, 0x047A, 1),      # Read 1 byte
    (0x40, 0x0C, 0x0000, 0x0475,          # Write 8 bytes: BOOT COMMAND
     bytes([0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x08, 0x01])),
]

TIMEOUT_MS = 5000
POLL_INTERVAL = 0.5
POLL_MAX = 40  # 20 seconds

# IOKit fires the launchd event before the device is fully enumerated
# in user-space, so we need to wait and retry device discovery
DISCOVERY_DELAY_S = 2.0     # Initial delay before first attempt
DISCOVERY_INTERVAL_S = 1.0  # Interval between retries
DISCOVERY_MAX_ATTEMPTS = 15 # 15 * 1.0s = 15s max wait for enumeration


# --- libusb device descriptor (matches C struct) ---

class libusb_device_descriptor(ctypes.Structure):
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16),
        ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8),
        ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8),
        ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16),
        ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8),
        ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8),
        ("bNumConfigurations", ctypes.c_uint8),
    ]


# --- libusb ctypes bindings (minimal) ---

def _load_libusb():
    """Load libusb-1.0 shared library and declare function signatures.

    CRITICAL: On arm64 (Apple Silicon), ctypes defaults to c_int return
    type (32-bit), but libusb returns 64-bit pointers. Without explicit
    restype declarations, pointer return values get truncated to 32 bits,
    making valid handles appear as NULL.
    """
    # Try common macOS paths
    paths = [
        "/opt/homebrew/lib/libusb-1.0.dylib",  # Apple Silicon brew
        "/usr/local/lib/libusb-1.0.dylib",     # Intel brew
        ctypes.util.find_library("usb-1.0"),    # System search
    ]
    lib = None
    for path in paths:
        if path and os.path.exists(path):
            try:
                lib = ctypes.cdll.LoadLibrary(path)
                break
            except OSError:
                continue

    if lib is None:
        lib_path = ctypes.util.find_library("usb-1.0")
        if lib_path:
            lib = ctypes.cdll.LoadLibrary(lib_path)
        else:
            raise RuntimeError(
                "libusb-1.0 not found. Install with: brew install libusb"
            )

    # --- Declare function signatures (critical for arm64!) ---

    # int libusb_init(libusb_context **)
    lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.libusb_init.restype = ctypes.c_int

    # void libusb_exit(libusb_context *)
    lib.libusb_exit.argtypes = [ctypes.c_void_p]
    lib.libusb_exit.restype = None

    # libusb_device_handle * libusb_open_device_with_vid_pid(ctx, vid, pid)
    lib.libusb_open_device_with_vid_pid.argtypes = [
        ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16
    ]
    lib.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p

    # void libusb_close(libusb_device_handle *)
    lib.libusb_close.argtypes = [ctypes.c_void_p]
    lib.libusb_close.restype = None

    # int libusb_control_transfer(handle, bmRequestType, bRequest,
    #                             wValue, wIndex, data, wLength, timeout)
    lib.libusb_control_transfer.argtypes = [
        ctypes.c_void_p,    # handle
        ctypes.c_uint8,     # bmRequestType
        ctypes.c_uint8,     # bRequest
        ctypes.c_uint16,    # wValue
        ctypes.c_uint16,    # wIndex
        ctypes.c_void_p,    # data
        ctypes.c_uint16,    # wLength
        ctypes.c_uint,      # timeout
    ]
    lib.libusb_control_transfer.restype = ctypes.c_int

    # ssize_t libusb_get_device_list(ctx, **list)
    lib.libusb_get_device_list.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ]
    lib.libusb_get_device_list.restype = ctypes.c_ssize_t

    # void libusb_free_device_list(list, unref_devices)
    lib.libusb_free_device_list.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_int
    ]
    lib.libusb_free_device_list.restype = None

    # int libusb_get_device_descriptor(dev, *desc)
    lib.libusb_get_device_descriptor.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(libusb_device_descriptor)
    ]
    lib.libusb_get_device_descriptor.restype = ctypes.c_int

    # int libusb_open(dev, **handle)
    lib.libusb_open.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    ]
    lib.libusb_open.restype = ctypes.c_int

    return lib


def log(msg):
    """Log to syslog (when running as daemon) and stderr."""
    syslog.syslog(syslog.LOG_NOTICE, f"u2702a-boot: {msg}")
    print(f"[u2702a-boot] {msg}", file=sys.stderr)


def _enumerate_devices(lib, ctx):
    """List all USB devices visible to libusb.

    Returns list of (vid, pid) tuples for diagnostics.
    """
    dev_list = ctypes.POINTER(ctypes.c_void_p)()
    count = lib.libusb_get_device_list(ctx, ctypes.byref(dev_list))
    if count < 0:
        log(f"libusb_get_device_list failed: {count}")
        return []

    devices = []
    for i in range(count):
        dev = dev_list[i]
        if not dev:
            break
        desc = libusb_device_descriptor()
        ret = lib.libusb_get_device_descriptor(dev, ctypes.byref(desc))
        if ret == 0:
            devices.append((desc.idVendor, desc.idProduct))

    lib.libusb_free_device_list(dev_list, 1)
    return devices


def _find_and_open_device(lib, ctx, vid, pid):
    """Find a device by VID/PID using enumeration, then try to open it.

    Returns (handle, error_code) where:
    - handle is non-None if device found and opened successfully
    - error_code is the libusb error if open failed, or None if not found
    """
    dev_list = ctypes.POINTER(ctypes.c_void_p)()
    count = lib.libusb_get_device_list(ctx, ctypes.byref(dev_list))
    if count < 0:
        return None, None

    handle = None
    error_code = None

    for i in range(count):
        dev = dev_list[i]
        if not dev:
            break
        desc = libusb_device_descriptor()
        ret = lib.libusb_get_device_descriptor(dev, ctypes.byref(desc))
        if ret != 0:
            continue
        if desc.idVendor == vid and desc.idProduct == pid:
            # Found the device — try to open it
            dev_handle = ctypes.c_void_p()
            ret = lib.libusb_open(dev, ctypes.byref(dev_handle))
            if ret == 0 and dev_handle.value:
                handle = dev_handle
            else:
                error_code = ret
            break

    lib.libusb_free_device_list(dev_list, 1)
    return handle, error_code


def _find_device_with_retry(lib):
    """Wait for the USB device to become visible to libusb.

    IOKit triggers the daemon before the device is fully enumerated,
    so we retry with fresh libusb contexts until the device appears.

    Uses low-level enumeration (libusb_get_device_list) to distinguish
    between "device not on bus" and "device found but can't open".

    Returns:
        (ctx, handle, pid) tuple, or (None, None, None) if not found.
    """
    log(f"Waiting {DISCOVERY_DELAY_S}s for USB enumeration...")
    time.sleep(DISCOVERY_DELAY_S)

    for attempt in range(DISCOVERY_MAX_ATTEMPTS):
        ctx = ctypes.c_void_p()
        ret = lib.libusb_init(ctypes.byref(ctx))
        if ret != 0:
            log(f"libusb_init failed: {ret}")
            time.sleep(DISCOVERY_INTERVAL_S)
            continue

        # Log all visible USB devices on first attempt (diagnostics)
        if attempt == 0:
            all_devs = _enumerate_devices(lib, ctx)
            agilent_devs = [(v, p) for v, p in all_devs if v == VID_AGILENT]
            log(f"Total USB devices visible: {len(all_devs)}")
            if agilent_devs:
                for v, p in agilent_devs:
                    log(f"  Agilent device: VID=0x{v:04X} PID=0x{p:04X}")
            else:
                log("  No Agilent devices found in enumeration")

        # Try to find and open operational device
        handle, err = _find_and_open_device(lib, ctx, VID_AGILENT, PID_OPERATIONAL)
        if handle is not None:
            log(f"Attempt {attempt + 1}: opened operational device")
            return ctx, handle, PID_OPERATIONAL
        if err is not None:
            log(f"Attempt {attempt + 1}: found operational device but "
                f"libusb_open failed: {err}")

        # Try to find and open boot-mode device
        handle, err = _find_and_open_device(lib, ctx, VID_AGILENT, PID_BOOT)
        if handle is not None:
            log(f"Attempt {attempt + 1}: opened boot-mode device")
            return ctx, handle, PID_BOOT
        if err is not None:
            log(f"Attempt {attempt + 1}: found boot device (PID 0x{PID_BOOT:04X}) "
                f"but libusb_open failed: error {err}")

        # Not found yet — release context and retry
        lib.libusb_exit(ctx)
        if attempt < DISCOVERY_MAX_ATTEMPTS - 1:
            # Re-enumerate on retries for diagnostics
            log(f"Attempt {attempt + 1}/{DISCOVERY_MAX_ATTEMPTS}: retrying...")
            time.sleep(DISCOVERY_INTERVAL_S)

    log(f"Device not found/openable after {DISCOVERY_MAX_ATTEMPTS} attempts")
    return None, None, None


def boot_device():
    """Find and boot U2702A from PID 0x2818 to 0x2918.

    Returns:
        True if boot succeeded or device already operational.
        False if no device found or boot failed.
    """
    lib = _load_libusb()
    log(f"Loaded libusb from: {lib._name}")
    log(f"Pointer size: {ctypes.sizeof(ctypes.c_void_p)} bytes "
        f"({'64-bit' if ctypes.sizeof(ctypes.c_void_p) == 8 else '32-bit'})")

    # Wait for device to become visible (IOKit fires before enumeration)
    ctx, handle, pid = _find_device_with_retry(lib)

    if ctx is None:
        log("No U2702A found on USB")
        return False

    try:
        if pid == PID_OPERATIONAL:
            log(f"Device already operational (PID 0x{PID_OPERATIONAL:04X})")
            lib.libusb_close(handle)
            return True

        # handle is for boot-mode device (PID_BOOT)
        log(f"Device found in boot mode (PID 0x{PID_BOOT:04X}). Booting...")

        # Send the 6-step boot sequence
        for i, transfer in enumerate(BOOT_SEQUENCE):
            bmRequestType, bRequest, wValue, wIndex, data_or_len = transfer

            if isinstance(data_or_len, int):
                # Read transfer: allocate buffer
                buf = (ctypes.c_uint8 * data_or_len)()
                ret = lib.libusb_control_transfer(
                    handle, bmRequestType, bRequest, wValue, wIndex,
                    buf, data_or_len, TIMEOUT_MS
                )
            else:
                # Write transfer: send data
                buf = (ctypes.c_uint8 * len(data_or_len))(*data_or_len)
                ret = lib.libusb_control_transfer(
                    handle, bmRequestType, bRequest, wValue, wIndex,
                    buf, len(data_or_len), TIMEOUT_MS
                )

            if ret < 0:
                log(f"Boot step {i + 1} failed: libusb error {ret}")
                lib.libusb_close(handle)
                return False

            log(f"Boot step {i + 1}/6 OK (wIndex=0x{wIndex:04X})")

        # Close the boot-mode handle
        lib.libusb_close(handle)
        log("Boot sequence sent. Waiting for re-enumeration...")

        # Release the original context before polling
        lib.libusb_exit(ctx)
        ctx = None  # Mark as released to prevent double-free in finally
        time.sleep(1.0)

        # Poll for operational device (fresh context each attempt)
        for attempt in range(POLL_MAX):
            poll_ctx = ctypes.c_void_p()
            lib.libusb_init(ctypes.byref(poll_ctx))

            handle2, err = _find_and_open_device(
                lib, poll_ctx, VID_AGILENT, PID_OPERATIONAL
            )
            if handle2 is not None:
                lib.libusb_close(handle2)
                lib.libusb_exit(poll_ctx)
                elapsed = (attempt + 1) * POLL_INTERVAL + 1.0
                log(f"Device operational (PID 0x{PID_OPERATIONAL:04X}) "
                    f"after {elapsed:.1f}s")
                return True

            lib.libusb_exit(poll_ctx)
            time.sleep(POLL_INTERVAL)

        log("TIMEOUT: device did not re-enumerate within 20s")
        return False

    finally:
        # Only exit ctx if it hasn't been released already
        if ctx is not None:
            try:
                lib.libusb_exit(ctx)
            except Exception:
                pass


if __name__ == "__main__":
    syslog.openlog("u2702a-boot", syslog.LOG_PID, syslog.LOG_DAEMON)
    log("Starting U2702A boot daemon")

    success = boot_device()

    if success:
        log("Boot complete - device ready")
        sys.exit(0)
    else:
        log("Boot failed")
        sys.exit(1)
