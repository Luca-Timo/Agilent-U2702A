"""
Keyboard-shortcuts reference dialog.

Groups the app's shortcuts by context (launcher, scope window,
instrument window) and renders them as a three-column table. Accessible
from the Help menu of every top-level window (Ctrl+/). The content is a
single source of truth — if you add a new shortcut somewhere in the app,
add it here too so the Help dialog stays honest.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)


# (section, (shortcut, description)) rows. Kept as a module-level table
# so the dialog renders fast and diffs against new bindings are obvious
# in code review.
_SHORTCUTS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Launcher window", [
        ("Ctrl+R",        "Refresh detected instruments"),
        ("Ctrl+Q",        "Quit LabTestBench"),
    ]),
    ("Oscilloscope window", [
        ("Ctrl+K",        "Show connection dialog"),
        ("Ctrl+O",        "Load session…"),
        ("Ctrl+S",        "Save session"),
        ("Ctrl+Shift+S",  "Save session as…"),
        ("Ctrl+I",        "Import waveform data"),
        ("Ctrl+E",        "Export…"),
        ("Ctrl+Shift+E",  "Quick-export CSV"),
        ("Ctrl+T",        "Open SCPI tester"),
        ("Ctrl+,",        "Open settings"),
        ("Ctrl+Z",        "Undo zoom"),
        ("Ctrl+W",        "Close window"),
        ("Ctrl+Q",        "Quit LabTestBench"),
    ]),
    ("Instrument window (DMM / function generator)", [
        ("Ctrl+W",        "Close window"),
    ]),
    ("Any window", [
        ("Ctrl+/",        "Show this Shortcuts dialog"),
        ("F1",            "Show Shortcuts dialog (alternate)"),
    ]),
]


class ShortcutsDialog(QDialog):
    """Keyboard-shortcut reference sheet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts — LabTestBench")
        self.setMinimumSize(520, 560)
        self.resize(560, 620)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        header = QLabel("Keyboard Shortcuts")
        hf = QFont()
        hf.setPointSize(16)
        hf.setBold(True)
        header.setFont(hf)
        root.addWidget(header)

        subtitle = QLabel(
            "Shortcuts are macOS-convention: on macOS, Cmd is used in "
            "place of Ctrl; on Windows and Linux, use Ctrl as shown."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888888;")
        root.addWidget(subtitle)

        root.addWidget(self._build_table())

        # OK-only button row
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    # -- UI helpers --------------------------------------------------

    def _build_table(self) -> QTableWidget:
        # Two columns: Shortcut | Action. Section headers are full-width
        # spans, bolded, with a subtle background.
        total_rows = sum(1 + len(rows) for _, rows in _SHORTCUTS)
        tbl = QTableWidget(total_rows, 2, self)
        tbl.setHorizontalHeaderLabels(["Shortcut", "Action"])
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setShowGrid(False)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = tbl.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        row = 0
        for section_name, rows in _SHORTCUTS:
            section_item = QTableWidgetItem(section_name)
            f = QFont()
            f.setBold(True)
            section_item.setFont(f)
            section_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tbl.setSpan(row, 0, 1, 2)
            tbl.setItem(row, 0, section_item)
            row += 1
            for shortcut, description in rows:
                sc_item = QTableWidgetItem(shortcut)
                mono = QFont("Menlo, Consolas, monospace")
                sc_item.setFont(mono)
                sc_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                tbl.setItem(row, 0, sc_item)
                desc_item = QTableWidgetItem(description)
                desc_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                tbl.setItem(row, 1, desc_item)
                row += 1
        return tbl


def install_shortcut_help(window) -> None:
    """Attach Ctrl+/ and F1 to open ``ShortcutsDialog`` on ``window``.

    Call this from every top-level window's ``__init__`` so the help
    sheet is discoverable everywhere. The dialog has no state — a new
    instance is constructed per open.
    """
    from PySide6.QtGui import QKeySequence, QShortcut

    def _show():
        ShortcutsDialog(parent=window).exec()

    for key in ("Ctrl+/", "F1"):
        sc = QShortcut(QKeySequence(key), window)
        sc.activated.connect(_show)
