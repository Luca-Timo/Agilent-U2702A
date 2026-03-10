"""
Measurement display bar — shows live measurements below the waveform.

Top row: measurement toggle buttons (select which measurements to display).
Below: one row per enabled channel showing active measurements.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
    QPushButton,
)

from gui.theme import (
    channel_color, format_voltage, format_frequency, format_time,
    NUM_CHANNELS, TEXT_SECONDARY, ACCENT_BLUE,
)


# Available measurement types and their display config
MEASUREMENT_TYPES = [
    ("Vpp",   "vpp",       format_voltage),
    ("Vmin",  "vmin",      format_voltage),
    ("Vmax",  "vmax",      format_voltage),
    ("Vrms",  "vrms",      format_voltage),
    ("Vmean", "vmean",     format_voltage),
    ("Freq",  "frequency", format_frequency),
    ("Period","period",     format_time),
]

# Measurements enabled by default
DEFAULT_ENABLED = {"Vpp", "Vmin", "Vmax", "Freq", "Period"}


class MeasurementButton(QPushButton):
    """Toggle button for a measurement type."""

    def __init__(self, name: str, parent=None):
        super().__init__(name, parent)
        self._name = name
        self.setCheckable(True)
        self.setChecked(name in DEFAULT_ENABLED)
        self.setFixedHeight(24)
        self.setMinimumWidth(48)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        self._update_style()
        self.toggled.connect(lambda _: self._update_style())

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(
                f"QPushButton {{ background-color: {ACCENT_BLUE}; "
                f"color: white; font-size: 10px; font-weight: bold; "
                f"border: 1px solid {ACCENT_BLUE}; border-radius: 3px; "
                f"padding: 1px 6px; }}"
                f"QPushButton:hover {{ background-color: #5aafff; }}"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background-color: #2a2a2a; "
                "color: #888888; font-size: 10px; "
                "border: 1px solid #444444; border-radius: 3px; "
                "padding: 1px 6px; }"
                "QPushButton:hover { border-color: #666666; color: #bbbbbb; }"
            )


class MeasurementRow(QFrame):
    """Single channel measurement row."""

    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self._channel = channel
        self._color = channel_color(channel)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"MeasurementRow {{ border: 1px solid {self._color}40; "
            f"border-radius: 3px; padding: 2px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(12)

        # Channel label
        ch_label = QLabel(f"CH{channel}")
        ch_label.setStyleSheet(
            f"color: {self._color}; font-weight: bold; font-size: 11px;"
        )
        ch_label.setFixedWidth(35)
        layout.addWidget(ch_label)

        # Measurement value labels — one for each measurement type
        self._labels: dict[str, QLabel] = {}
        for display_name, _, _ in MEASUREMENT_TYPES:
            lbl = QLabel(f"{display_name}: ---")
            lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 11px; "
                "font-family: Menlo, monospace;"
            )
            self._labels[display_name] = lbl
            layout.addWidget(lbl)

        layout.addStretch()

    def set_measurement_visible(self, name: str, visible: bool):
        """Show or hide a specific measurement label."""
        if name in self._labels:
            self._labels[name].setVisible(visible)

    def update_measurements(self, meas: dict):
        """Update measurement display.

        Args:
            meas: Dict from processing.measurements.compute_all()
        """
        for display_name, key, fmt_func in MEASUREMENT_TYPES:
            lbl = self._labels.get(display_name)
            if lbl is None:
                continue
            val = meas.get(key)
            if val is not None:
                lbl.setText(f"{display_name}: {fmt_func(val)}")
            else:
                lbl.setText(f"{display_name}: ---")

    def clear(self):
        """Reset all measurements to ---."""
        for display_name, _, _ in MEASUREMENT_TYPES:
            lbl = self._labels.get(display_name)
            if lbl:
                lbl.setText(f"{display_name}: ---")


class MeasurementBar(QWidget):
    """Measurement display bar with toggle buttons and per-channel rows.

    Signals:
        measurement_toggled(str, bool) — measurement type toggled on/off
    """

    measurement_toggled = Signal(str, bool)

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__(parent)
        self._num_channels = num_channels
        self._rows: dict[int, MeasurementRow] = {}
        self._buttons: dict[str, MeasurementButton] = {}
        self._enabled_measurements: set[str] = set(DEFAULT_ENABLED)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        # --- Measurement toggle buttons row ---
        btn_frame = QFrame()
        btn_frame.setStyleSheet(
            "QFrame { border: 1px solid #333333; border-radius: 3px; "
            "padding: 2px; }"
        )
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(4, 2, 4, 2)
        btn_layout.setSpacing(4)

        meas_label = QLabel("Meas:")
        meas_label.setStyleSheet(
            "color: #888888; font-size: 10px; font-weight: bold; border: none;"
        )
        btn_layout.addWidget(meas_label)

        for display_name, _, _ in MEASUREMENT_TYPES:
            btn = MeasurementButton(display_name)
            btn.toggled.connect(
                lambda checked, name=display_name: self._on_measurement_toggled(
                    name, checked
                )
            )
            self._buttons[display_name] = btn
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        self._layout.addWidget(btn_frame)

        # --- Per-channel measurement rows ---
        for ch in range(1, num_channels + 1):
            row = MeasurementRow(ch)
            row.setVisible(False)
            self._rows[ch] = row
            self._layout.addWidget(row)

        # Apply initial visibility
        self._apply_measurement_visibility()

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Minimum)

    def _on_measurement_toggled(self, name: str, checked: bool):
        """Handle measurement button toggle."""
        if checked:
            self._enabled_measurements.add(name)
        else:
            self._enabled_measurements.discard(name)
        self._apply_measurement_visibility()
        self.measurement_toggled.emit(name, checked)

    def _apply_measurement_visibility(self):
        """Update visibility of measurement labels in all rows."""
        for row in self._rows.values():
            for display_name, _, _ in MEASUREMENT_TYPES:
                row.set_measurement_visible(
                    display_name, display_name in self._enabled_measurements
                )

    def set_channel_visible(self, channel: int, visible: bool):
        """Show or hide a channel's measurement row."""
        if channel in self._rows:
            self._rows[channel].setVisible(visible)

    def update_measurements(self, channel: int, meas: dict):
        """Update measurements for a channel."""
        if channel in self._rows:
            self._rows[channel].update_measurements(meas)

    def clear_channel(self, channel: int):
        """Clear measurements for a channel."""
        if channel in self._rows:
            self._rows[channel].clear()

    def clear_all(self):
        """Clear all measurement displays."""
        for row in self._rows.values():
            row.clear()
