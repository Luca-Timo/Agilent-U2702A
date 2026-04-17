# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the U2702A lab-bench app.

Produces a standalone ``LabBench`` executable that bundles Python,
PySide6, PyQtGraph, numpy, and every instrument/processing/gui module
into one directory (``--onedir``) or one file (``--onefile`` — set
ONEFILE=1 when invoking). Platform-specific output:

    macOS:   dist/LabBench.app           (onedir) or dist/LabBench (onefile)
    Windows: dist/LabBench/LabBench.exe  (onedir) or dist/LabBench.exe (onefile)
    Linux:   dist/LabBench/LabBench      (onedir) or dist/LabBench (onefile)

Invoke via ``scripts/build_app.py``; don't run pyinstaller on this
spec directly unless you know what you're doing — the wrapper sets
REPO_ROOT and validates the environment.
"""

import os
import sys
from pathlib import Path

# The spec file is executed by pyinstaller with a custom globals dict,
# so ``__file__`` is the spec path. Project root is one level up.
SPEC_DIR = Path(os.environ.get("REPO_ROOT", Path(SPECPATH).parent))
ONEFILE = os.environ.get("ONEFILE", "0") == "1"

APP_NAME = "LabBench"
ENTRY_POINT = str(SPEC_DIR / "gui" / "main.py")

# PySide6 + PyQtGraph + pyvisa-py have submodules PyInstaller's
# auto-discovery misses in some Python versions. List them explicitly.
hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtPrintSupport",   # QPdfWriter in gui/graph_renderer.py
    "pyqtgraph",
    "pyqtgraph.Qt",
    "numpy",
    "serial",
    "serial.tools.list_ports",
    # pyvisa-py isn't used on the ESP32 serial path but the import
    # lives in instrument/connection.py (fallback for direct-USB mode)
    # and PyInstaller will warn if it's missing. Safe to include.
    "pyvisa",
]

# Data files we need inside the bundle.
datas = []
# Ship presets + config; they're Python so auto-discovery finds them
# anyway, but this makes it explicit so nothing slips through on a
# bad cache.
for pkg in ("config", "instrument", "processing", "gui", "automation"):
    pkg_dir = SPEC_DIR / pkg
    if pkg_dir.exists():
        for py in pkg_dir.rglob("*.py"):
            rel = py.relative_to(SPEC_DIR)
            datas.append((str(py), str(rel.parent)))


a = Analysis(
    [ENTRY_POINT],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Things PySide6's auto-import pulls in that we never use —
        # trimming keeps the bundle size down.
        "PySide6.QtMultimedia",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineCore",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,       # host arch; CI picks per-OS runners
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )

# On macOS, wrap into a .app bundle (onedir only — onefile on macOS
# is fine as a raw executable but not as a .app).
if sys.platform == "darwin" and not ONEFILE:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=None,
        bundle_identifier="com.u2702a.labbench",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": "U2702A Lab Bench",
            "CFBundleShortVersionString": "0.10.0-alpha",
            "CFBundleVersion": "0.10.0-alpha",
            "NSHighResolutionCapable": "True",
        },
    )
