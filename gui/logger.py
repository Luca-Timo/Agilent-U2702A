"""
Structured logging setup.

Writes to ``~/.config/U2702A/oscilloscope.log`` (rotating) plus stderr so
the user has a persistent record of warnings/errors across runs.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


LOG_DIR = Path.home() / ".config" / "U2702A"
LOG_FILE = LOG_DIR / "oscilloscope.log"
_MAX_BYTES = 2 * 1024 * 1024   # 2 MB
_BACKUP_COUNT = 3


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure root logger exactly once. Returns the root logger.

    Idempotent: calling a second time is a no-op.
    """
    root = logging.getLogger()
    if getattr(root, "_u2702a_configured", False):
        return root

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.setLevel(logging.WARNING)  # stderr: warnings+ only

    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root._u2702a_configured = True   # type: ignore[attr-defined]

    # PyQtGraph and PySide are chatty at DEBUG; silence unless explicitly asked.
    logging.getLogger("PyQt6").setLevel(logging.WARNING)
    logging.getLogger("pyqtgraph").setLevel(logging.WARNING)

    root.info("Logging initialised at %s", LOG_FILE)
    return root
