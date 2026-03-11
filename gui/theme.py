"""
Dark theme and styling for the oscilloscope GUI.

Provides dark Fusion palette, default channel colors, and SI unit formatting.
"""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt


# --- Number of channels (change this for 4/8-channel scopes) ---
NUM_CHANNELS = 2

# --- Default channel colors (up to 8 channels) ---
DEFAULT_CHANNEL_COLORS = [
    "#FFD700",  # CH1 — gold/yellow
    "#00FFFF",  # CH2 — cyan
    "#FF6B6B",  # CH3 — coral red
    "#7CFC00",  # CH4 — lawn green
    "#FF69B4",  # CH5 — hot pink
    "#FFA500",  # CH6 — orange
    "#8A2BE2",  # CH7 — blue violet
    "#00FF7F",  # CH8 — spring green
]

# --- UI colors ---
BG_DARK = "#1a1a1a"
BG_MEDIUM = "#2a2a2a"
BG_LIGHT = "#3a3a3a"
BG_PLOT = "#0a0a0a"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#888888"
TEXT_DIM = "#555555"
GRID_COLOR = "#333333"
BORDER_COLOR = "#444444"
ACCENT_BLUE = "#4a9eff"
STATUS_GREEN = "#50c878"
STATUS_YELLOW = "#ffcc00"
STATUS_RED = "#ff5555"

# --- 1-2-5 value sequences ---

VDIV_VALUES = [
    0.002, 0.005,
    0.010, 0.020, 0.050,
    0.100, 0.200, 0.500,
    1.000, 2.000, 5.000,
    10.00,
]

TDIV_VALUES = [
    5e-9, 10e-9, 20e-9, 50e-9,
    100e-9, 200e-9, 500e-9,
    1e-6, 2e-6, 5e-6,
    10e-6, 20e-6, 50e-6,
    100e-6, 200e-6, 500e-6,
    1e-3, 2e-3, 5e-3,
    10e-3, 20e-3, 50e-3,
    100e-3, 200e-3, 500e-3,
    1.0, 2.0, 5.0,
    10.0, 20.0, 50.0,
]


# --- SI prefix formatting ---

_SI_PREFIXES = [
    (1e-9, "n"),
    (1e-6, "\u00b5"),  # µ
    (1e-3, "m"),
    (1.0, ""),
    (1e3, "k"),
    (1e6, "M"),
]


def format_si(value: float, unit: str = "", precision: int = 3) -> str:
    """Format a value with SI prefix.

    Examples:
        format_si(0.005, "V") -> "5.00 mV"
        format_si(1e-3, "s") -> "1.00 ms"
        format_si(1000, "Hz") -> "1.00 kHz"
    """
    if value == 0:
        return f"0 {unit}"

    abs_val = abs(value)
    for scale, prefix in reversed(_SI_PREFIXES):
        if abs_val >= scale * 0.999:
            scaled = value / scale
            return f"{scaled:.{precision-1}f} {prefix}{unit}".strip()

    # Very small — use ns
    scaled = value / 1e-9
    return f"{scaled:.{precision-1}f} n{unit}".strip()


def format_vdiv(value: float) -> str:
    """Format V/div value."""
    return format_si(value, "V/div")


def format_tdiv(value: float) -> str:
    """Format T/div value."""
    return format_si(value, "s/div")


def format_voltage(value: float) -> str:
    """Format a voltage value."""
    return format_si(value, "V")


def format_time(value: float) -> str:
    """Format a time value."""
    return format_si(value, "s")


def format_frequency(value: float) -> str:
    """Format a frequency value."""
    return format_si(value, "Hz")


def format_percent(value: float) -> str:
    """Format a percentage value (e.g. duty cycle)."""
    return f"{value:.1f}%"


def channel_color(ch: int) -> str:
    """Get default color for channel number (1-indexed)."""
    idx = (ch - 1) % len(DEFAULT_CHANNEL_COLORS)
    return DEFAULT_CHANNEL_COLORS[idx]


def apply_dark_theme(app: QApplication):
    """Apply dark Fusion theme to the application."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_MEDIUM))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_LIGHT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_MEDIUM))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_LIGHT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.WindowText, QColor(TEXT_DIM))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.Text, QColor(TEXT_DIM))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.ButtonText, QColor(TEXT_DIM))

    app.setPalette(palette)

    # Global stylesheet refinements
    app.setStyleSheet("""
        QGroupBox {
            border: 1px solid #444444;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 12px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        QComboBox {
            padding: 3px 6px;
            border: 1px solid #444444;
            border-radius: 3px;
        }
        QPushButton {
            padding: 4px 12px;
            border: 1px solid #444444;
            border-radius: 3px;
            background-color: #3a3a3a;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
        }
        QPushButton:pressed {
            background-color: #2a2a2a;
        }
        QToolTip {
            background-color: #2a2a2a;
            color: #e0e0e0;
            border: 1px solid #444444;
            padding: 4px;
        }
    """)
