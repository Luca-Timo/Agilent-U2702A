"""
Math operation control panel — enable + operation selector.

Controls channel math (CH1+CH2, CH1-CH2, CH1*CH2, CH1/CH2).
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QLabel


class MathPanel(QGroupBox):
    """Math operation controls.

    Signals:
        math_toggled(bool) — math display enabled/disabled
        math_op_changed(str) — "add", "sub", "mul", "div"
    """

    math_toggled = Signal(bool)
    math_op_changed = Signal(str)

    _OPS = [
        ("add", "CH1 + CH2"),
        ("sub", "CH1 − CH2"),
        ("mul", "CH1 × CH2"),
        ("div", "CH1 ÷ CH2"),
    ]

    def __init__(self, parent=None):
        super().__init__("MATH", parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self._enable_cb = QCheckBox("Enable Math")
        self._enable_cb.toggled.connect(self._on_toggled)
        layout.addWidget(self._enable_cb)

        row = QHBoxLayout()
        row.addWidget(QLabel("Operation:"))
        self._op_combo = QComboBox()
        for _, label in self._OPS:
            self._op_combo.addItem(label)
        self._op_combo.currentIndexChanged.connect(self._on_op_changed)
        self._op_combo.setEnabled(False)
        row.addWidget(self._op_combo)
        layout.addLayout(row)

    def _on_toggled(self, checked: bool):
        self._op_combo.setEnabled(checked)
        self.math_toggled.emit(checked)

    def _on_op_changed(self, index: int):
        if 0 <= index < len(self._OPS):
            self.math_op_changed.emit(self._OPS[index][0])

    # --- Public API ---

    @property
    def enabled(self) -> bool:
        return self._enable_cb.isChecked()

    @property
    def operation(self) -> str:
        idx = self._op_combo.currentIndex()
        return self._OPS[idx][0] if 0 <= idx < len(self._OPS) else "add"

    def set_enabled(self, enabled: bool):
        self._enable_cb.setChecked(enabled)

    def set_operation(self, op: str):
        for i, (key, _) in enumerate(self._OPS):
            if key == op:
                self._op_combo.setCurrentIndex(i)
                return
