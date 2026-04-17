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

# Hidden imports PyInstaller's auto-discovery can miss. Keep this list
# SMALL — every entry forces Analysis to follow extra dependency trees.
# In particular do NOT list ``pyvisa``: it's only imported by
# ``instrument/connection.py`` (a dev-only fallback, never reached from
# gui/main.py) and its pyvisa-py backends have platform-specific
# dynamic imports that trip PyInstaller on Linux / Windows.
hidden_imports = [
    "PySide6.QtPrintSupport",    # QPdfWriter in gui/graph_renderer.py
    "pyqtgraph",
    "serial.tools.list_ports",
]

# ``datas`` stays empty. Analysis walks imports from gui/main.py and
# bundles every pure-Python module it reaches into the PYZ archive —
# no need to copy .py files as data. Earlier revisions of this spec
# duplicated every module into ``datas`` which silently worked on
# macOS but caused cross-platform path / duplicate-file issues on
# the CI Linux and Windows runners.
datas = []


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
        # Never reached from gui/main.py — excluding keeps the bundle
        # smaller AND avoids Analysis trying to resolve their deps.
        # pyvisa / pyvisa-py / pyusb are only in the dev-only direct-USB
        # path (instrument/connection.py, used by test_connection.py).
        "pyvisa",
        "pyvisa_py",
        "usb",
        # PySide6 modules we don't use.
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
