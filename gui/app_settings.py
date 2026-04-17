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
    # When True, the connection dialog probes every serial port with
    # *IDN? on open to auto-identify the attached instrument. Disable
    # if probing interferes with a third-party device on the same bus
    # or slows the dialog open too much.
    auto_discovery_enabled: bool = True
    # "dark" (default) or "light". Applied at app start from
    # gui/main.py; live-switching is not supported — the Settings
    # dialog tells the user to restart.
    theme_mode: str = "dark"


# Module-level singleton — import as ``from gui.app_settings import SETTINGS``.
SETTINGS = _AppSettings()
