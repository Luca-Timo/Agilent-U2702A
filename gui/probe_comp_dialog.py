"""
Probe Compensation Check — informational guidance dialog.

Shows instructions for adjusting the probe compensation trimmer
using the scope's built-in calibration output.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox,
)


class ProbeCompensationDialog(QDialog):
    """Guidance dialog for probe compensation adjustment."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Probe Compensation Check")
        self.setMinimumSize(500, 400)
        self.resize(540, 440)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("<h3>Probe Compensation Adjustment</h3>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Instructions
        instructions = QLabel(
            "<ol>"
            "<li>Connect the probe tip to the <b>CAL</b> output "
            "on the front panel.</li>"
            "<li>Connect the ground clip to the scope's ground terminal.</li>"
            "<li>Set the scope to display the calibration signal:<br>"
            "&nbsp;&nbsp;&nbsp;CH1, 1 V/div, 500 \u00b5s/div, Auto trigger.</li>"
            "<li>You should see a 1 kHz square wave.</li>"
            "<li>Adjust the compensation trimmer screw on the probe "
            "body until the square wave edges are sharp with no "
            "overshoot or rounding.</li>"
            "</ol>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("font-size: 12px; padding: 8px;")
        layout.addWidget(instructions)

        # Visual reference
        ref_label = QLabel("<b>Visual Reference:</b>")
        ref_label.setStyleSheet("padding-left: 8px;")
        layout.addWidget(ref_label)

        waveforms = QLabel(
            "  Correct:              Under-compensated:      Over-compensated:\n"
            "\n"
            "   \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2510"
            "                \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2510"
            "                \u256d\u2500\u2500\u2500\u2500\u2500\u2500\u256e\n"
            "   \u2502      \u2502"
            "                \u2502     \u2572"
            "                \u2502      \u2502\n"
            " \u2500\u2500\u2518      \u2514\u2500\u2500"
            "            \u2500\u2500\u2571       \u2514\u2500\u2500"
            "            \u2500\u2500\u2518      \u2570\u2500\u2500\n"
            "\n"
            "  (flat top/bottom)     (rounded edges)         (overshoot/ringing)"
        )
        waveforms.setStyleSheet(
            "font-family: Menlo, monospace; font-size: 11px; "
            "background-color: #1a1a1a; padding: 12px; "
            "border: 1px solid #333333; border-radius: 4px;"
        )
        layout.addWidget(waveforms)

        layout.addStretch()

        # OK button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
