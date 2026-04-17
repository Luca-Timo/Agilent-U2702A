"""
App-wide settings singleton for user preferences that live between widgets.

Prefer this over class-level variables on widgets — class attributes leak
across instances and are hard to reason about in a multi-window world.
Add new user preferences here as simple fields; persistence is handled
by gui/session.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _AppSettings:
    knob_scroll_enabled: bool = False


# Module-level singleton — import as ``from gui.app_settings import SETTINGS``.
SETTINGS = _AppSettings()
