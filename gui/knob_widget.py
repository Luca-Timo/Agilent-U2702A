"""
Custom rotary knob widget for oscilloscope controls.

Features:
  - Circular painted knob with indicator line
  - Click-and-drag vertically to step through values
  - Click the value label → popup editor (Enter to apply, Escape to cancel)
  - Mouse wheel to step ±1
  - Supports discrete value lists (1-2-5 sequence) or continuous range
"""

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QRadialGradient,
    QConicalGradient, QPainterPath,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QSizePolicy, QApplication,
)


class ValuePopup(QLineEdit):
    """Frameless popup editor for entering values."""

    value_submitted = Signal(str)
    cancelled = Signal()

    def __init__(self, current_text: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(current_text)
        self.selectAll()
        self.setFixedWidth(120)
        self.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 2px solid #4a9eff;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
                font-family: Menlo, monospace;
            }
        """)

        self.returnPressed.connect(self._submit)

    def _submit(self):
        self.value_submitted.emit(self.text())
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.cancelled.emit()
        self.close()
        super().focusOutEvent(event)


class RotaryKnob(QWidget):
    """Custom rotary knob control.

    Emits value_changed(float) when the user adjusts the value.
    """

    value_changed = Signal(float)

    # Knob drawing constants
    KNOB_DIAMETER = 52
    ARC_START_ANGLE = 225    # degrees (bottom-left)
    ARC_SPAN = -270          # degrees (clockwise)

    # Class-level setting: when False, scroll wheel on knobs is ignored
    _scroll_enabled: bool = True

    @classmethod
    def set_scroll_enabled(cls, enabled: bool):
        """Enable or disable scroll-wheel adjustment on all knobs."""
        cls._scroll_enabled = enabled

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)

        self._label = label
        self._values: list[float] = []
        self._value_index = 0
        self._value = 0.0
        self._format_func = None  # Custom format function

        # Continuous mode
        self._continuous = False
        self._center_zero = False  # Bipolar arc (center = 0)
        self._min_val = 0.0
        self._max_val = 1.0
        self._step = 0.1

        # Drag state
        self._dragging = False
        self._drag_start_y = 0
        self._drag_accumulated = 0.0
        self._drag_total_distance = 0.0
        self._drag_threshold = 15  # pixels per step

        # Layout
        self._setup_ui()
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(self.KNOB_DIAMETER + 10, self.KNOB_DIAMETER + 44)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Label above knob
        self._label_widget = QLabel(self._label)
        self._label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_widget.setStyleSheet(
            "color: #888888; font-size: 10px; font-weight: bold;"
        )
        layout.addWidget(self._label_widget)

        # Spacer for knob (painted in paintEvent)
        layout.addSpacing(self.KNOB_DIAMETER + 4)

        # Value label (clickable)
        self._value_label = QLabel("0")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_label.setStyleSheet(
            "color: #e0e0e0; font-size: 11px; font-family: Menlo, monospace;"
            "padding: 2px; border-radius: 3px;"
        )
        self._value_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._value_label.mousePressEvent = self._on_value_click
        layout.addWidget(self._value_label)

    def set_values(self, values: list[float], index: int = 0):
        """Set discrete value list (e.g., 1-2-5 sequence)."""
        self._values = list(values)
        self._continuous = False
        self._value_index = max(0, min(index, len(self._values) - 1))
        self._value = self._values[self._value_index]
        self._update_display()

    def set_range(self, min_val: float, max_val: float, step: float,
                  initial: float = None):
        """Set continuous value range."""
        self._continuous = True
        self._min_val = min_val
        self._max_val = max_val
        self._step = step
        self._value = initial if initial is not None else min_val
        # Auto-detect bipolar: arc sweeps from center when range spans zero
        self._center_zero = (min_val < 0 and max_val > 0)
        self._update_display()

    def set_format_func(self, func):
        """Set custom format function for the value display."""
        self._format_func = func
        self._update_display()

    @property
    def value(self) -> float:
        return self._value

    def set_value(self, value: float, emit: bool = False):
        """Set value programmatically."""
        if self._continuous:
            self._value = max(self._min_val, min(self._max_val, value))
        else:
            # Find closest value in list
            if self._values:
                closest_idx = min(
                    range(len(self._values)),
                    key=lambda i: abs(self._values[i] - value)
                )
                self._value_index = closest_idx
                self._value = self._values[closest_idx]
        self._update_display()
        if emit:
            self.value_changed.emit(self._value)

    def _step_value(self, direction: int):
        """Step value up (+1) or down (-1)."""
        old_value = self._value

        if self._continuous:
            self._value += direction * self._step
            self._value = max(self._min_val, min(self._max_val, self._value))
        else:
            if self._values:
                self._value_index += direction
                self._value_index = max(0, min(len(self._values) - 1,
                                               self._value_index))
                self._value = self._values[self._value_index]

        if self._value != old_value:
            self._update_display()
            self.value_changed.emit(self._value)

    def _update_display(self):
        """Update the value label text."""
        if self._format_func:
            text = self._format_func(self._value)
        else:
            text = f"{self._value:.4g}"
        self._value_label.setText(text)
        self.update()  # Repaint knob

    def _knob_rect(self) -> QRectF:
        """Get the knob drawing rectangle."""
        w = self.width()
        d = self.KNOB_DIAMETER
        x = (w - d) / 2
        y = 20  # Below the label
        return QRectF(x, y, d, d)

    def _value_fraction(self) -> float:
        """Get current value as 0..1 fraction of range."""
        if self._continuous:
            rng = self._max_val - self._min_val
            if rng <= 0:
                return 0.5
            return (self._value - self._min_val) / rng
        else:
            if len(self._values) <= 1:
                return 0.5
            return self._value_index / (len(self._values) - 1)

    # --- Paint ---

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._knob_rect()
        center = rect.center()
        radius = rect.width() / 2

        # Knob body — radial gradient
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, QColor("#555555"))
        gradient.setColorAt(0.7, QColor("#3a3a3a"))
        gradient.setColorAt(1.0, QColor("#2a2a2a"))

        painter.setPen(QPen(QColor("#555555"), 1.5))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(rect)

        # Arc track (background)
        track_rect = rect.adjusted(3, 3, -3, -3)
        pen = QPen(QColor("#333333"), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(track_rect,
                        self.ARC_START_ANGLE * 16,
                        self.ARC_SPAN * 16)

        # Arc track (active portion)
        frac = self._value_fraction()
        pen = QPen(QColor("#4a9eff"), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if self._center_zero:
            # Bipolar: arc from center (12 o'clock = 0) toward current value
            center_angle = self.ARC_START_ANGLE + self.ARC_SPAN * 0.5
            active_span = int(self.ARC_SPAN * (frac - 0.5))
            if active_span != 0:
                painter.drawArc(track_rect,
                                int(center_angle * 16),
                                active_span * 16)
        else:
            # Unipolar: arc from start to current value
            active_span = int(self.ARC_SPAN * frac)
            if active_span != 0:
                painter.drawArc(track_rect,
                                self.ARC_START_ANGLE * 16,
                                active_span * 16)

        # Indicator line
        angle_deg = self.ARC_START_ANGLE + self.ARC_SPAN * frac
        angle_rad = math.radians(angle_deg)
        inner_r = radius * 0.3
        outer_r = radius * 0.75
        x1 = center.x() + inner_r * math.cos(angle_rad)
        y1 = center.y() - inner_r * math.sin(angle_rad)
        x2 = center.x() + outer_r * math.cos(angle_rad)
        y2 = center.y() - outer_r * math.sin(angle_rad)

        painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))

        # Center dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#666666"))
        painter.drawEllipse(center, 3, 3)

        painter.end()

    # --- Mouse interaction ---
    # Click (no drag) = open value popup
    # Click + drag = adjust value by dragging up/down
    # Scroll wheel = also adjusts value

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self._knob_rect()
            if rect.contains(event.position()):
                self._dragging = True
                self._drag_start_y = event.position().y()
                self._drag_accumulated = 0.0
                self._drag_total_distance = 0.0  # Track if user actually dragged
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dy = self._drag_start_y - event.position().y()  # Up = positive
            self._drag_accumulated += dy
            self._drag_total_distance += abs(dy)
            self._drag_start_y = event.position().y()

            steps = int(self._drag_accumulated / self._drag_threshold)
            if steps != 0:
                self._drag_accumulated -= steps * self._drag_threshold
                for _ in range(abs(steps)):
                    self._step_value(1 if steps > 0 else -1)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

            # If user barely moved, treat as click → open popup
            if self._drag_total_distance < 5:
                self._open_value_popup()

            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self._scroll_enabled:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._step_value(1)
        elif delta < 0:
            self._step_value(-1)
        event.accept()

    def _on_value_click(self, event):
        """Open popup editor when value label is clicked."""
        self._open_value_popup()

    def _open_value_popup(self):
        """Open the value editor popup."""
        popup = ValuePopup(self._value_label.text(), self)
        popup.value_submitted.connect(self._on_popup_value)

        # Position popup below the knob
        knob_rect = self._knob_rect()
        global_pos = self.mapToGlobal(
            QPoint(int(knob_rect.center().x()) - 60,
                   int(knob_rect.bottom()) + 8)
        )
        popup.move(global_pos)
        popup.show()
        popup.setFocus()

    def _on_popup_value(self, text: str):
        """Handle value submitted from popup."""
        text = text.strip()
        # Parse SI suffixes
        multipliers = {
            'n': 1e-9, 'u': 1e-6, '\u00b5': 1e-6, 'm': 1e-3,
            'k': 1e3, 'M': 1e6,
        }

        # Try to extract number and optional suffix
        try:
            # Remove common unit suffixes
            for unit in ['V/div', 's/div', 'V', 's', 'Hz']:
                text = text.replace(unit, '').strip()

            # Check for SI prefix at end
            multiplier = 1.0
            if text and text[-1] in multipliers:
                multiplier = multipliers[text[-1]]
                text = text[:-1].strip()

            value = float(text) * multiplier
            self.set_value(value, emit=True)

        except (ValueError, IndexError):
            pass  # Invalid input — ignore

    def sizeHint(self):
        return QSize(self.KNOB_DIAMETER + 16, self.KNOB_DIAMETER + 48)
