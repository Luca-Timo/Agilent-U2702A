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

from PySide6.QtWidgets import QApplication
from gui.logger import setup_logging
from gui.theme import apply_dark_theme
from gui.launcher_window import LauncherWindow


def main():
    setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Lab Bench")
    app.setApplicationVersion("0.11.0-alpha")

    apply_dark_theme(app)

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
