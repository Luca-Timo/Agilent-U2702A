"""
FFT control panel — enable, source channel, Y scale, window function.

Sits in the right sidebar. Controls which channel's FFT is computed
and how it's displayed in the split-view FFT pane.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QLabel,
)


class FFTPanel(QGroupBox):
    """FFT display controls.

    Signals:
        fft_toggled(bool) — FFT display enabled/disabled
        fft_source_changed(int) — source channel number (1, 2, ...)
        fft_scale_changed(str) — "dbv" or "linear"
        fft_window_changed(str) — "hann", "hamming", "blackman", "rect"
    """

    fft_toggled = Signal(bool)
    fft_source_changed = Signal(int)
    fft_scale_changed = Signal(str)
    fft_window_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("FFT", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Enable checkbox
        self._enable_cb = QCheckBox("Enable FFT")
        self._enable_cb.toggled.connect(self._on_toggled)
        layout.addWidget(self._enable_cb)

        # Note: FFT requires split view
        self._note = QLabel("Requires Split Channels view")
        self._note.setStyleSheet("font-size: 9px; color: #888888; font-style: italic;")
        layout.addWidget(self._note)

        # Source channel
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Source:"))
        self._source_combo = QComboBox()
        self._source_combo.addItems(["CH1", "CH2"])
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        self._source_combo.setEnabled(False)
        row1.addWidget(self._source_combo)
        layout.addLayout(row1)

        # Y Scale
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Y Scale:"))
        self._scale_combo = QComboBox()
        self._scale_combo.addItems(["dBV", "Linear V"])
        self._scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        self._scale_combo.setEnabled(False)
        row2.addWidget(self._scale_combo)
        layout.addLayout(row2)

        # Window function
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Window:"))
        self._window_combo = QComboBox()
        self._window_combo.addItems(["Hann", "Hamming", "Blackman", "Rectangular"])
        self._window_combo.currentIndexChanged.connect(self._on_window_changed)
        self._window_combo.setEnabled(False)
        row3.addWidget(self._window_combo)
        layout.addLayout(row3)

    def _on_toggled(self, checked: bool):
        self._source_combo.setEnabled(checked)
        self._scale_combo.setEnabled(checked)
        self._window_combo.setEnabled(checked)
        self.fft_toggled.emit(checked)

    def _on_source_changed(self, index: int):
        self.fft_source_changed.emit(index + 1)  # 1-based channel

    def _on_scale_changed(self, index: int):
        self.fft_scale_changed.emit("dbv" if index == 0 else "linear")

    def _on_window_changed(self, index: int):
        windows = ["hann", "hamming", "blackman", "rect"]
        self.fft_window_changed.emit(windows[index])

    # --- Public API ---

    @property
    def enabled(self) -> bool:
        return self._enable_cb.isChecked()

    @property
    def source_channel(self) -> int:
        return self._source_combo.currentIndex() + 1

    @property
    def scale(self) -> str:
        return "dbv" if self._scale_combo.currentIndex() == 0 else "linear"

    @property
    def window(self) -> str:
        windows = ["hann", "hamming", "blackman", "rect"]
        return windows[self._window_combo.currentIndex()]

    def set_enabled(self, enabled: bool):
        self._enable_cb.setChecked(enabled)

    def set_source(self, channel: int):
        self._source_combo.setCurrentIndex(channel - 1)

    def set_scale(self, scale: str):
        self._scale_combo.setCurrentIndex(0 if scale == "dbv" else 1)

    def set_window(self, window: str):
        windows = ["hann", "hamming", "blackman", "rect"]
        if window in windows:
            self._window_combo.setCurrentIndex(windows.index(window))
