"""
The ``InstrumentDriver`` protocol — the seam between transport and UI.

Every instrument we support implements this interface. The GUI and the
automation layer both call driver methods; there is no "API vs GUI"
divergence. Rules enforced by design:

- Drivers never import from ``gui/``. They get a ``Bridge`` and a
  ``Capabilities``, nothing else.
- Methods are synchronous. The worker thread wraps them for the GUI;
  scripts call them directly.
- State changes emit on the driver itself (not a widget) so both the
  GUI and automation subscribers see the same event stream.

A driver owns its SCPI dialect, its acquisition loop, and its setting
semantics. Everything else (transport, threading, display) is external
and pluggable.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from instrument.capabilities import Capabilities


@runtime_checkable
class Bridge(Protocol):
    """Duck-typed transport interface already implemented by
    ``SerialBridge`` and ``DemoBridge``. Formalised here so drivers and
    tests can depend on a named type instead of a comment.
    """

    is_open: bool
    bridge_status: str
    port: str

    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, command: str, timeout: Optional[float] = None) -> str: ...
    def query(self, command: str, timeout: Optional[float] = None) -> str: ...
    def query_binary(
        self, command: str, timeout: Optional[float] = None,
    ) -> bytes: ...
    def wait_for_status(
        self, target: str = "READY", timeout: float = 30.0,
    ) -> str: ...


@runtime_checkable
class InstrumentDriver(Protocol):
    """The contract every concrete instrument driver implements.

    This is deliberately small; instrument-kind specifics (e.g. scope
    triggers, DMM measurement modes) live on the concrete driver and are
    reached via ``apply_setting`` / ``read_setting`` so generic callers
    stay simple.
    """

    capabilities: Capabilities
    bridge: Bridge

    # Lifecycle -------------------------------------------------------
    def open(self) -> None:
        """Open the bridge and run any per-instrument setup."""

    def close(self) -> None:
        """Close the bridge cleanly."""

    def init_sequence(self) -> dict:
        """One-shot state query run after connect.

        Returns a nested dict describing the instrument's current
        state (channels, modes, ranges, etc.). The GUI uses this to
        populate control panels; scripts can inspect it.
        """

    # Acquisition -----------------------------------------------------
    def acquire(self) -> Optional[Any]:
        """Perform one acquisition step and return the result.

        The concrete return type matches ``capabilities.acquisition_model``:
        - WAVEFORM → a ``WaveformData`` (or bundle of them, one per
          enabled channel; see ``acquire_all``)
        - SCALAR → a ``MeterReading``
        - SETPOINT → a ``GeneratorState``

        Returns ``None`` if the instrument is not ready or the user
        cancelled mid-acquisition. Never raises for normal "no data
        yet"; raises on transport errors only.
        """

    # Generic setting access -----------------------------------------
    def apply_setting(self, key: str, value: Any) -> None:
        """Generic setter for instrument settings keyed by string.

        Example keys (scope): "channel.1.vdiv", "trigger.level",
        "timebase.tdiv". The driver owns the key namespace; callers
        discover keys via ``supported_settings``.
        """

    def read_setting(self, key: str) -> Any:
        """Generic getter, symmetric with ``apply_setting``."""

    def supported_settings(self) -> tuple[str, ...]:
        """Enumerate the keys this driver understands.

        Used by automation tooling to generate help / introspection.
        """
