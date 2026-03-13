"""
Settings dialog — display colors, probe config, controls.

Tabbed dialog: Display, Controls, Probes.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QComboBox, QPushButton, QGroupBox, QGridLayout,
    QCheckBox, QSpinBox, QColorDialog, QFrame, QInputDialog,
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
        knob_scroll_changed(bool) — knob scroll wheel enabled/disabled
    """

    channel_color_changed = Signal(int, str)
    line_width_changed = Signal(int)
    knob_scroll_changed = Signal(bool)

    def __init__(self, num_channels: int = NUM_CHANNELS,
                 current_colors: dict = None,
                 current_probes: dict = None,
                 knob_scroll_enabled: bool = True,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(400, 340)
        self.resize(450, 380)

        self._num_channels = num_channels
        self._colors = current_colors or {}
        self._probes = current_probes or {}
        self._color_buttons: dict[int, ColorButton] = {}
        self._knob_scroll_enabled = knob_scroll_enabled
        self._prev_probe_idx: dict[int, int] = {}

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

        # --- Controls tab ---
        controls_tab = QWidget()
        controls_layout = QVBoxLayout(controls_tab)

        knob_group = QGroupBox("Knob Behavior")
        knob_layout = QVBoxLayout()

        self._scroll_checkbox = QCheckBox("Enable scroll wheel on knobs")
        self._scroll_checkbox.setChecked(self._knob_scroll_enabled)
        self._scroll_checkbox.setToolTip(
            "When disabled, scroll wheel won't accidentally change\n"
            "V/div, T/div, or other knob values while scrolling."
        )
        self._scroll_checkbox.toggled.connect(self._on_scroll_toggled)
        knob_layout.addWidget(self._scroll_checkbox)

        scroll_note = QLabel(
            "Tip: Disabling scroll prevents accidental value changes\n"
            "when scrolling the control panel. You can still drag\n"
            "the knob or click to enter a value."
        )
        scroll_note.setStyleSheet(
            "color: #666666; font-size: 10px; padding-top: 4px;"
        )
        knob_layout.addWidget(scroll_note)

        knob_group.setLayout(knob_layout)
        controls_layout.addWidget(knob_group)

        controls_layout.addStretch()
        tabs.addTab(controls_tab, "Controls")

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
            combo.addItems(["1x", "10x", "100x", "1000x", "Custom..."])
            combo.currentTextChanged.connect(
                lambda text, c=ch: self._on_probe_combo_changed(c, text)
            )

            # Pre-select current probe factor
            factor = self._probes.get(ch, 1.0)
            text = f"{factor:g}x"
            idx = combo.findText(text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                # Custom value — replace last item text
                last = combo.count() - 1
                combo.setItemText(last, text)
                combo.setCurrentIndex(last)
            self._prev_probe_idx[ch] = combo.currentIndex()

            self._probe_combos[ch] = combo
            probe_grid.addWidget(combo, ch - 1, 1)

        note = QLabel("Note: Probe attenuation is software-only.\n"
                       "No SCPI command is sent to the instrument.")
        note.setStyleSheet("color: #666666; font-size: 10px; padding-top: 8px;")
        probe_grid.addWidget(note, self._num_channels, 0, 1, 2)

        probe_group.setLayout(probe_grid)
        probe_layout.addWidget(probe_group)

        # Probe compensation button
        comp_btn = QPushButton("Probe Compensation Check...")
        comp_btn.setFixedHeight(32)
        comp_btn.clicked.connect(self._show_probe_compensation)
        probe_layout.addWidget(comp_btn)

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

    def _on_scroll_toggled(self, checked: bool):
        self._knob_scroll_enabled = checked
        self.knob_scroll_changed.emit(checked)

    def _on_probe_combo_changed(self, ch: int, text: str):
        if text == "Custom...":
            combo = self._probe_combos[ch]
            current = self._probes.get(ch, 1.0)
            value, ok = QInputDialog.getDouble(
                self, "Custom Probe Factor",
                f"Probe attenuation for CH{ch}:",
                value=current, min=0.001, max=10000.0, decimals=3,
            )
            if ok and value > 0:
                combo.blockSignals(True)
                idx = combo.count() - 1
                combo.setItemText(idx, f"{value:g}x")
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)
                self._prev_probe_idx[ch] = idx
                self._probes[ch] = value
            else:
                combo.blockSignals(True)
                combo.setCurrentIndex(self._prev_probe_idx.get(ch, 0))
                combo.blockSignals(False)
            return
        combo = self._probe_combos[ch]
        self._prev_probe_idx[ch] = combo.currentIndex()
        self._probes[ch] = float(text.replace("x", ""))

    def _show_probe_compensation(self):
        from gui.probe_comp_dialog import ProbeCompensationDialog
        dialog = ProbeCompensationDialog(self)
        dialog.exec()

    def get_colors(self) -> dict[int, str]:
        return dict(self._colors)

    def get_probe_factors(self) -> dict[int, float]:
        result = {}
        for ch, combo in self._probe_combos.items():
            text = combo.currentText()
            result[ch] = float(text.replace("x", ""))
        return result

    def is_knob_scroll_enabled(self) -> bool:
        return self._knob_scroll_enabled

    def get_line_width(self) -> int:
        return self._line_width_spin.value()
