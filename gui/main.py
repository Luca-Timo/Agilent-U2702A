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
from gui.theme import apply_dark_theme
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Agilent U2702A Oscilloscope")
    app.setApplicationVersion("0.8.1-alpha")

    apply_dark_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
