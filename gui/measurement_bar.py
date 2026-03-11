"""
Measurement display bar — table layout with column headers and aligned values.

Top row: measurement toggle buttons (select which columns to display).
Below: table with header row + one row per enabled channel.
"""

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy, QPushButton,
)

from gui.theme import (
    channel_color, format_voltage, format_frequency, format_time,
    format_percent, NUM_CHANNELS, TEXT_SECONDARY, ACCENT_BLUE,
)


# Available measurement types: (display_name, dict_key, format_func)
MEASUREMENT_TYPES = [
    ("Vpp",    "vpp",       format_voltage),
    ("Vmin",   "vmin",      format_voltage),
    ("Vmax",   "vmax",      format_voltage),
    ("Vrms",   "vrms",      format_voltage),
    ("Vmean",  "vmean",     format_voltage),
    ("Freq",   "frequency", format_frequency),
    ("Period", "period",    format_time),
    ("Rise",   "rise_time", format_time),
    ("Fall",   "fall_time", format_time),
    ("Duty",   "duty_cycle", format_percent),
]

# Measurements enabled by default
DEFAULT_ENABLED = {"Vpp", "Vmin", "Vmax", "Freq", "Period"}

# Column width for measurement values (monospace characters)
COL_MIN_WIDTH = 90


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


class MeasurementBar(QWidget):
    """Measurement display bar — table with header + per-channel value rows.

    Layout:
        [Meas: [Vpp] [Vmin] [Vmax] [Vrms] [Vmean] [Freq] [Period]  ]
        ┌──────┬──────────┬──────────┬──────────┬──────────┬──────────┐
        │      │   Vpp    │   Vmin   │   Vmax   │   Freq   │  Period  │
        ├──────┼──────────┼──────────┼──────────┼──────────┼──────────┤
        │ CH1  │  3.12 V  │ -312 mV  │  2.81 V  │ 1.00 kHz │ 995 µs  │
        │ CH2  │  312 mV  │ -31.2 mV │  281 mV  │ 1.00 kHz │ 995 µs  │
        └──────┴──────────┴──────────┴──────────┴──────────┴──────────┘

    Signals:
        measurement_toggled(str, bool) — measurement type toggled on/off
    """

    measurement_toggled = Signal(str, bool)

    # Emitted when user hovers a value cell: (channel, display_name, raw_meas_dict)
    value_hovered = Signal(int, str, dict)
    # Emitted when hover leaves a value cell
    value_unhovered = Signal()

    def __init__(self, num_channels: int = NUM_CHANNELS, parent=None):
        super().__init__(parent)
        self._num_channels = num_channels
        self._buttons: dict[str, MeasurementButton] = {}
        self._enabled_measurements: set[str] = set(DEFAULT_ENABLED)

        # Header labels (one per measurement type)
        self._header_labels: dict[str, QLabel] = {}
        # Value labels: _value_labels[channel][display_name] = QLabel
        self._value_labels: dict[int, dict[str, QLabel]] = {}
        # Channel label + row frame for visibility toggling
        self._channel_labels: dict[int, QLabel] = {}
        self._channel_visible: dict[int, bool] = {}

        # Raw measurement values per channel (for hover cursors)
        self._last_measurements: dict[int, dict] = {}

        self._build_ui()

        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Minimum)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # --- Toggle buttons row ---
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
        outer.addWidget(btn_frame)

        # --- Measurement table (grid) ---
        table_frame = QFrame()
        table_frame.setStyleSheet(
            "QFrame { border: 1px solid #333333; border-radius: 3px; }"
        )
        self._table_frame = table_frame

        grid = QGridLayout(table_frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self._grid = grid

        # Column 0 = channel label, columns 1..N = measurement values
        # Row 0 = header, rows 1..M = channels

        # Header row — column 0 is empty
        spacer = QLabel("")
        spacer.setFixedWidth(50)
        spacer.setStyleSheet("border: none;")
        grid.addWidget(spacer, 0, 0)

        for col_idx, (display_name, _, _) in enumerate(MEASUREMENT_TYPES):
            lbl = QLabel(display_name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter)
            lbl.setMinimumWidth(COL_MIN_WIDTH)
            lbl.setStyleSheet(
                "color: #888888; font-size: 10px; font-weight: bold; "
                "font-family: Menlo, monospace; "
                "border: none; border-bottom: 1px solid #333333; "
                "padding: 2px 8px;"
            )
            self._header_labels[display_name] = lbl
            grid.addWidget(lbl, 0, col_idx + 1)

        # Channel value rows
        for ch in range(1, self._num_channels + 1):
            row_idx = ch  # row 0 = header, row 1 = CH1, row 2 = CH2, ...
            color = channel_color(ch)

            # Channel label in column 0
            ch_lbl = QLabel(f"  CH{ch}")
            ch_lbl.setFixedWidth(50)
            ch_lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 11px; "
                "border: none; padding: 2px 4px;"
            )
            self._channel_labels[ch] = ch_lbl
            grid.addWidget(ch_lbl, row_idx, 0)

            # Value labels for each measurement type
            self._value_labels[ch] = {}
            for col_idx, (display_name, _, _) in enumerate(MEASUREMENT_TYPES):
                val_lbl = QLabel("---")
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
                val_lbl.setMinimumWidth(COL_MIN_WIDTH)
                val_lbl.setStyleSheet(
                    f"color: {color}; font-size: 11px; "
                    "font-family: Menlo, monospace; "
                    "border: none; padding: 2px 8px;"
                )
                # Store channel + measurement name for hover lookup
                val_lbl.setProperty("meas_ch", ch)
                val_lbl.setProperty("meas_name", display_name)
                val_lbl.setMouseTracking(True)
                val_lbl.installEventFilter(self)
                self._value_labels[ch][display_name] = val_lbl
                grid.addWidget(val_lbl, row_idx, col_idx + 1)

            self._channel_visible[ch] = False

        outer.addWidget(table_frame)

        # Apply initial visibility
        self._apply_column_visibility()
        self._apply_row_visibility()

    def _on_measurement_toggled(self, name: str, checked: bool):
        """Handle measurement button toggle."""
        if checked:
            self._enabled_measurements.add(name)
        else:
            self._enabled_measurements.discard(name)
        self._apply_column_visibility()
        self.measurement_toggled.emit(name, checked)

    def _apply_column_visibility(self):
        """Show/hide entire columns (header + all channel values)."""
        for display_name, _, _ in MEASUREMENT_TYPES:
            visible = display_name in self._enabled_measurements
            # Header
            self._header_labels[display_name].setVisible(visible)
            # All channel values
            for ch in range(1, self._num_channels + 1):
                self._value_labels[ch][display_name].setVisible(visible)

    def _apply_row_visibility(self):
        """Show/hide channel rows and the entire table frame."""
        any_visible = False
        for ch in range(1, self._num_channels + 1):
            visible = self._channel_visible.get(ch, False)
            self._channel_labels[ch].setVisible(visible)
            for lbl in self._value_labels[ch].values():
                lbl.setVisible(
                    visible and self._find_display_name(lbl) in self._enabled_measurements
                )
            if visible:
                any_visible = True
        self._table_frame.setVisible(any_visible)

    def _find_display_name(self, lbl: QLabel) -> str:
        """Find the display_name for a value label (reverse lookup)."""
        for ch_labels in self._value_labels.values():
            for name, l in ch_labels.items():
                if l is lbl:
                    return name
        return ""

    def set_channel_visible(self, channel: int, visible: bool):
        """Show or hide a channel's measurement row."""
        self._channel_visible[channel] = visible
        self._apply_row_visibility()

    def eventFilter(self, obj, event):
        """Detect hover enter/leave on measurement value labels."""
        if event.type() == QEvent.Type.Enter:
            ch = obj.property("meas_ch")
            name = obj.property("meas_name")
            if ch is not None and name is not None:
                meas = self._last_measurements.get(ch, {})
                if meas:
                    self.value_hovered.emit(ch, name, meas)
            return False
        if event.type() == QEvent.Type.Leave:
            self.value_unhovered.emit()
            return False
        return super().eventFilter(obj, event)

    def update_measurements(self, channel: int, meas: dict):
        """Update measurements for a channel."""
        if channel not in self._value_labels:
            return
        self._last_measurements[channel] = dict(meas)
        for display_name, key, fmt_func in MEASUREMENT_TYPES:
            lbl = self._value_labels[channel].get(display_name)
            if lbl is None:
                continue
            val = meas.get(key)
            if val is not None:
                lbl.setText(fmt_func(val))
            else:
                lbl.setText("---")

    def clear_channel(self, channel: int):
        """Clear measurements for a channel."""
        if channel not in self._value_labels:
            return
        self._last_measurements.pop(channel, None)
        for lbl in self._value_labels[channel].values():
            lbl.setText("---")

    def clear_all(self):
        """Clear all measurement displays."""
        self._last_measurements.clear()
        for ch in self._value_labels:
            self.clear_channel(ch)
