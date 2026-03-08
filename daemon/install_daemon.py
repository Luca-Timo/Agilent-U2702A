#!/usr/bin/env python3
"""
U2702A Boot Daemon Installer/Uninstaller

Compiles and installs a native IOKit-based macOS launchd daemon that
automatically boots the U2702A from firmware-update mode (PID 0x2818)
to operational USBTMC mode (PID 0x2918) whenever it's plugged in.

Requires: Xcode Command Line Tools (for cc compiler)

Usage:
    sudo python3 daemon/install_daemon.py              # Install
    sudo python3 daemon/install_daemon.py --uninstall  # Uninstall
    python3 daemon/install_daemon.py --status           # Check status
"""

import os
import subprocess
import sys

DAEMON_LABEL = "com.u2702a.boot"
PLIST_INSTALL_PATH = f"/Library/LaunchDaemons/{DAEMON_LABEL}.plist"
DAEMON_INSTALL_DIR = "/usr/local/lib/u2702a"
HELPER_INSTALL_PATH = f"{DAEMON_INSTALL_DIR}/u2702a_boot_helper"

# Source paths (relative to this script)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLIST_SOURCE = os.path.join(SCRIPT_DIR, f"{DAEMON_LABEL}.plist")
C_SOURCE = os.path.join(SCRIPT_DIR, "u2702a_boot_helper.c")


def check_root():
    if os.geteuid() != 0:
        print("ERROR: This script must be run with sudo.")
        print(f"  sudo python3 {' '.join(sys.argv)}")
        sys.exit(1)


def check_compiler():
    """Verify Xcode Command Line Tools are installed."""
    result = subprocess.run(
        ["xcode-select", "-p"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERROR: Xcode Command Line Tools not found.")
        print("  Install with: xcode-select --install")
        sys.exit(1)


def compile_helper():
    """Compile the C boot helper."""
    print("  Compiling native IOKit boot helper...")

    result = subprocess.run(
        [
            "cc",
            "-framework", "IOKit",
            "-framework", "CoreFoundation",
            "-Wall", "-O2",
            "-o", HELPER_INSTALL_PATH,
            C_SOURCE,
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"  COMPILE FAILED:")
        print(result.stderr)
        sys.exit(1)

    # Set ownership and permissions
    os.chown(HELPER_INSTALL_PATH, 0, 0)   # root:wheel
    os.chmod(HELPER_INSTALL_PATH, 0o755)   # rwxr-xr-x
    print(f"  Helper binary: {HELPER_INSTALL_PATH} (root:wheel, 755)")


def install():
    """Install the boot daemon."""
    check_root()
    check_compiler()

    print("Installing U2702A boot daemon...")
    print()

    # Verify source files exist
    if not os.path.exists(C_SOURCE):
        print(f"ERROR: Source not found: {C_SOURCE}")
        print("  Run from the project directory.")
        sys.exit(1)

    # 1. Create install directory (owned by root:wheel)
    os.makedirs(DAEMON_INSTALL_DIR, exist_ok=True)
    os.chown(DAEMON_INSTALL_DIR, 0, 0)
    os.chmod(DAEMON_INSTALL_DIR, 0o755)

    # 2. Compile and install the C helper
    compile_helper()

    # 3. Create plist with correct path
    with open(PLIST_SOURCE, "r") as f:
        plist_content = f.read()

    plist_content = plist_content.replace("__HELPER_PATH__", HELPER_INSTALL_PATH)

    with open(PLIST_INSTALL_PATH, "w") as f:
        f.write(plist_content)

    os.chmod(PLIST_INSTALL_PATH, 0o644)
    os.chown(PLIST_INSTALL_PATH, 0, 0)
    print(f"  LaunchDaemon:  {PLIST_INSTALL_PATH}")

    # 4. Load the daemon
    subprocess.run(
        ["launchctl", "unload", PLIST_INSTALL_PATH],
        capture_output=True,
    )
    result = subprocess.run(
        ["launchctl", "load", PLIST_INSTALL_PATH],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"  WARNING: launchctl load returned: {result.stderr.strip()}")
    else:
        print("  Daemon loaded successfully.")

    print()
    print("Done! The daemon will now automatically boot the U2702A")
    print("whenever it's plugged in via USB.")
    print()
    print("Test by unplugging and re-plugging the oscilloscope.")
    print(f"Logs: /var/log/u2702a-boot.log")


def uninstall():
    """Uninstall the boot daemon."""
    check_root()

    print("Uninstalling U2702A boot daemon...")
    print()

    # 1. Unload daemon
    if os.path.exists(PLIST_INSTALL_PATH):
        subprocess.run(
            ["launchctl", "unload", PLIST_INSTALL_PATH],
            capture_output=True,
        )
        os.remove(PLIST_INSTALL_PATH)
        print(f"  Removed: {PLIST_INSTALL_PATH}")
    else:
        print(f"  Not found: {PLIST_INSTALL_PATH}")

    # 2. Remove helper binary
    if os.path.exists(HELPER_INSTALL_PATH):
        os.remove(HELPER_INSTALL_PATH)
        print(f"  Removed: {HELPER_INSTALL_PATH}")
    else:
        print(f"  Not found: {HELPER_INSTALL_PATH}")

    # 3. Remove old Python script if present
    old_script = f"{DAEMON_INSTALL_DIR}/u2702a_boot.py"
    if os.path.exists(old_script):
        os.remove(old_script)
        print(f"  Removed: {old_script} (legacy)")

    # 4. Remove directory if empty
    if os.path.exists(DAEMON_INSTALL_DIR):
        try:
            os.rmdir(DAEMON_INSTALL_DIR)
            print(f"  Removed: {DAEMON_INSTALL_DIR}")
        except OSError:
            pass

    print()
    print("Daemon uninstalled.")


def status():
    """Check daemon status (no sudo needed)."""
    print("U2702A Boot Daemon Status")
    print("-" * 40)

    # Check plist
    if os.path.exists(PLIST_INSTALL_PATH):
        print(f"  Plist:  {PLIST_INSTALL_PATH} (installed)")
    else:
        print(f"  Plist:  NOT INSTALLED")
        print()
        print("Install with: sudo python3 daemon/install_daemon.py")
        return

    # Check helper binary
    if os.path.exists(HELPER_INSTALL_PATH):
        print(f"  Helper: {HELPER_INSTALL_PATH} (installed)")
    else:
        print(f"  Helper: MISSING")

    # Check if loaded
    result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True, text=True,
    )
    if DAEMON_LABEL in result.stdout:
        print(f"  Status: LOADED (active)")
    else:
        print(f"  Status: NOT LOADED")

    # Check log
    log_path = "/var/log/u2702a-boot.log"
    if os.path.exists(log_path):
        size = os.path.getsize(log_path)
        print(f"  Log:    {log_path} ({size} bytes)")
        with open(log_path, "r") as f:
            lines = f.readlines()
            if lines:
                print()
                print("  Last log entries:")
                for line in lines[-5:]:
                    print(f"    {line.rstrip()}")
    else:
        print(f"  Log:    (no log yet)")


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    elif "--status" in sys.argv:
        status()
    else:
        install()
