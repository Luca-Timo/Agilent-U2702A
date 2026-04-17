"""
Prominent output-enable widget for signal-producing instruments.

The BNC either has signal on it or it doesn't — the UI should make
which state the user is in unmistakable. Gray when off, red when on;
large fixed-width label; clickable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPushButton


class OutputIndicator(QPushButton):
    """Toggle button for instrument output enable.

    Emits ``toggled(bool)`` on user click (inherited from QPushButton).
    Programmatic updates via ``set_output(bool)`` do NOT emit — use
    those when reflecting instrument state from ``driver.acquire()``
    so the UI doesn't feed back into itself.
    """

    # Colour constants pulled locally instead of from theme.py because
    # the output-on red needs to be distinct from the theme's STATUS_RED
    # (which is used for error text) and more saturated than the scope
    # trigger colour.
    _OFF_STYLE = (
        "QPushButton { "
        "  background-color: #2a2a2a; "
        "  color: #888888; "
        "  border: 2px solid #444444; "
        "  border-radius: 8px; "
        "  font-size: 18px; "
        "  font-weight: bold; "
        "  padding: 12px 20px; "
        "}"
        "QPushButton:hover { border-color: #666666; }"
    )
    _ON_STYLE = (
        "QPushButton { "
        "  background-color: #cc3030; "
        "  color: #ffffff; "
        "  border: 2px solid #ff6060; "
        "  border-radius: 8px; "
        "  font-size: 18px; "
        "  font-weight: bold; "
        "  padding: 12px 20px; "
        "}"
        "QPushButton:hover { background-color: #dd3a3a; }"
    )

    LABEL_OFF = "OUTPUT  OFF"
    LABEL_ON = "OUTPUT  ON"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setMinimumHeight(64)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.setFont(font)
        self._apply_style(False)
        self.setText(self.LABEL_OFF)
        # Toggle the visual when the user clicks — and keep it in sync
        # with programmatic updates via set_output().
        self.toggled.connect(self._apply_style)
        self.toggled.connect(
            lambda on: self.setText(self.LABEL_ON if on else self.LABEL_OFF)
        )

    # -- Public API ---------------------------------------------------

    def set_output(self, enabled: bool) -> None:
        """Programmatic update that reflects instrument state.

        Emits ``toggled`` only if the state actually changed (Qt's
        default) — but the change is driven from the driver, not the
        user, so the driver-side setter must be guarded against
        re-emitting to avoid an infinite loop. Standard pattern:
        ``blockSignals(True)`` around this call from the result handler.
        """
        if self.isChecked() == enabled:
            return
        self.blockSignals(True)
        try:
            self.setChecked(enabled)
            self._apply_style(enabled)
            self.setText(self.LABEL_ON if enabled else self.LABEL_OFF)
        finally:
            self.blockSignals(False)

    # -- Internal -----------------------------------------------------

    def _apply_style(self, on: bool) -> None:
        self.setStyleSheet(self._ON_STYLE if on else self._OFF_STYLE)
