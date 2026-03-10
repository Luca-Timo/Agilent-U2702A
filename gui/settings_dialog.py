"""
Settings dialog — display colors, probe config, connection info.

Tabbed dialog: Display, Probes.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QComboBox, QPushButton, QGroupBox, QGridLayout,
    QCheckBox, QSpinBox, QColorDialog, QFrame,
)
from PySide6.QtGui import QColor

from gui.theme import channel_color, NUM_CHANNELS


class ColorButton(QPushButton):
    """Button that shows/picks a color."""

    color_changed = Signal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(40, 24)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _update_style(self):
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color}; "
            f"border: 2px solid #555555; border-radius: 3px; }}"
            f"QPushButton:hover {{ border-color: #888888; }}"
        )

    def _pick_color(self):
        color = QColorDialog.getColor(
            QColor(self._color), self, "Choose Channel Color"
        )
        if color.isValid():
            self._color = color.name()
            self._update_style()
            self.color_changed.emit(self._color)

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str):
        self._color = color
        self._update_style()


class SettingsDialog(QDialog):
    """Application settings dialog.

    Signals:
        channel_color_changed(int, str) — channel color changed
        line_width_changed(int) — waveform line width changed
    """

    channel_color_changed = Signal(int, str)
    line_width_changed = Signal(int)

    def __init__(self, num_channels: int = NUM_CHANNELS,
                 current_colors: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(400, 300)
        self.resize(450, 350)

        self._num_channels = num_channels
        self._colors = current_colors or {}
        self._color_buttons: dict[int, ColorButton] = {}

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # --- Display tab ---
        display_tab = QWidget()
        display_layout = QVBoxLayout(display_tab)

        # Channel colors
        color_group = QGroupBox("Channel Colors")
        color_grid = QGridLayout()

        for ch in range(1, self._num_channels + 1):
            color = self._colors.get(ch, channel_color(ch))
            label = QLabel(f"CH{ch}:")
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            color_grid.addWidget(label, ch - 1, 0)

            btn = ColorButton(color)
            btn.color_changed.connect(
                lambda c, channel=ch: self._on_color_changed(channel, c)
            )
            self._color_buttons[ch] = btn
            color_grid.addWidget(btn, ch - 1, 1)

            # Color name label
            name_label = QLabel(color)
            name_label.setStyleSheet("color: #888888; font-size: 10px;")
            color_grid.addWidget(name_label, ch - 1, 2)

        color_group.setLayout(color_grid)
        display_layout.addWidget(color_group)

        # Line width
        lw_group = QGroupBox("Waveform")
        lw_layout = QHBoxLayout()
        lw_layout.addWidget(QLabel("Line Width:"))
        self._line_width_spin = QSpinBox()
        self._line_width_spin.setRange(1, 5)
        self._line_width_spin.setValue(2)
        self._line_width_spin.valueChanged.connect(
            lambda v: self.line_width_changed.emit(v)
        )
        lw_layout.addWidget(self._line_width_spin)
        lw_layout.addStretch()
        lw_group.setLayout(lw_layout)
        display_layout.addWidget(lw_group)

        display_layout.addStretch()
        tabs.addTab(display_tab, "Display")

        # --- Probes tab ---
        probe_tab = QWidget()
        probe_layout = QVBoxLayout(probe_tab)

        probe_group = QGroupBox("Probe Attenuation")
        probe_grid = QGridLayout()

        self._probe_combos: dict[int, QComboBox] = {}
        for ch in range(1, self._num_channels + 1):
            color = self._colors.get(ch, channel_color(ch))
            label = QLabel(f"CH{ch}:")
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            probe_grid.addWidget(label, ch - 1, 0)

            combo = QComboBox()
            combo.addItems(["1x", "10x"])
            self._probe_combos[ch] = combo
            probe_grid.addWidget(combo, ch - 1, 1)

        note = QLabel("Note: Probe attenuation is software-only.\n"
                       "No SCPI command is sent to the instrument.")
        note.setStyleSheet("color: #666666; font-size: 10px; padding-top: 8px;")
        probe_grid.addWidget(note, self._num_channels, 0, 1, 2)

        probe_group.setLayout(probe_grid)
        probe_layout.addWidget(probe_group)
        probe_layout.addStretch()
        tabs.addTab(probe_tab, "Probes")

        layout.addWidget(tabs)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _on_color_changed(self, ch: int, color: str):
        self._colors[ch] = color
        self.channel_color_changed.emit(ch, color)

    def get_colors(self) -> dict[int, str]:
        return dict(self._colors)

    def get_probe_factors(self) -> dict[int, float]:
        result = {}
        for ch, combo in self._probe_combos.items():
            text = combo.currentText()
            result[ch] = float(text.replace("x", ""))
        return result
