"""
ActionRecorder — capture a sequence of driver calls for replay.

A GUI session records every ``apply_setting`` and acquire call. The
recording is a list of :class:`Action` entries that can be saved to
JSON and replayed against the same (or a different) driver later.

This is the smallest useful form of "record / replay" automation. It
ignores timing — actions run back-to-back with no inter-action delay —
which is fine for configuration sequences and test setups. Add a
``delay`` field later if time-sensitive replays are needed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from instrument.driver import InstrumentDriver


@dataclass
class Action:
    """One recorded driver call."""

    method: str                     # "apply_setting" | "acquire"
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


class ActionRecorder:
    """Capture driver calls into a replayable list.

    Typical usage: wrap a driver, call methods on the recorder, it
    forwards to the driver and remembers every call. The GUI can
    attach a recorder when the user hits a "record" button, capturing
    every setting change until "stop".
    """

    def __init__(self, driver: InstrumentDriver) -> None:
        self._driver = driver
        self._actions: list[Action] = []
        self._recording: bool = False

    # -- Recording control -------------------------------------------

    def start(self) -> None:
        self._recording = True

    def stop(self) -> None:
        self._recording = False

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def actions(self) -> tuple[Action, ...]:
        return tuple(self._actions)

    def clear(self) -> None:
        self._actions.clear()

    # -- Recording the set of methods that make up an "action" -------

    def apply_setting(self, key: str, value: Any) -> None:
        self._driver.apply_setting(key, value)
        if self._recording:
            self._actions.append(Action("apply_setting", args=(key, value)))

    def acquire(self, **kwargs) -> Any:
        result = self._driver.acquire(**kwargs)
        if self._recording:
            self._actions.append(Action("acquire", kwargs=dict(kwargs)))
        return result

    # -- Persistence --------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Write recorded actions to a JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump([asdict(a) for a in self._actions], f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> list[Action]:
        """Read a saved action list (does not require a driver)."""
        with open(path, "r") as f:
            raw = json.load(f)
        return [
            Action(
                method=a["method"],
                args=tuple(a.get("args", ())),
                kwargs=a.get("kwargs", {}),
            )
            for a in raw
        ]

    @staticmethod
    def replay(driver: InstrumentDriver, actions: list[Action]) -> list[Any]:
        """Execute a list of actions against ``driver``.

        Returns the list of results from every call; non-returning
        actions contribute ``None``.
        """
        results: list[Any] = []
        for action in actions:
            if action.method == "apply_setting":
                driver.apply_setting(*action.args)
                results.append(None)
            elif action.method == "acquire":
                results.append(driver.acquire(**action.kwargs))
            else:
                raise ValueError(f"Unknown action method {action.method!r}")
        return results
