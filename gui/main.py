"""
Entry point for the Agilent U2702A Oscilloscope GUI.

Usage:
    python gui/main.py
    python -m gui.main
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from gui.app_settings import SETTINGS
from gui.logger import setup_logging
from gui.theme import apply_theme
from gui.launcher_window import LauncherWindow


def main():
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("LabTestBench")
    app.setApplicationVersion("1.0.0-beta")

    # Theme choice is persisted via QSettings (separate from session
    # files so it survives even when the user nukes their session
    # state). Read it BEFORE applying the palette — Qt palette
    # changes don't propagate cleanly once widgets are built, so we
    # need the right theme on first paint.
    qs = QSettings("AgilentU2702A", "LTB")
    SETTINGS.theme_mode = qs.value("theme_mode", "dark", type=str)
    apply_theme(app, SETTINGS.theme_mode)

    # LauncherWindow is the new top-level. It shows scanned devices
    # plus a demo section for every registered model, and spawns
    # per-instrument windows on demand. Closing the launcher quits
    # the app (after confirming with the user if any instrument
    # windows are still open).
    launcher = LauncherWindow()
    launcher.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
