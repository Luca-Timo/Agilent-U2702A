"""
LabSession — open drivers by name, tear them all down on exit.

The automation-layer entry point. Scripts call ``LabSession.open(model)``
to get a driver bound to a live bridge; context-manager exit closes
every driver it opened, in LIFO order.

Bridge selection:
  - ``demo=True`` forces a DemoBridge (no hardware)
  - ``port="/dev/..."`` forces a specific serial port
  - otherwise :func:`auto_discover_port` picks the first CP2102N-style
    serial adapter. If none is found, falls back to demo mode.
"""

from __future__ import annotations

import logging
from typing import Optional

from config import (
    DMMConfig,
    FunctionGeneratorConfig,
    InstrumentConfig,
    REGISTRY,
)
from instrument.demo_bridge import DemoBridge
from instrument.demo_dmm_bridge import DemoDMMBridge
from instrument.demo_funcgen_bridge import DemoFuncGenBridge
from instrument.discovery import DiscoveredInstrument, discover
from instrument.driver import Bridge, InstrumentDriver
from instrument.serial_bridge import SerialBridge, list_serial_ports

logger = logging.getLogger(__name__)


# Map from model name → driver class. Expanded as new drivers land.
# Keeping this table in the session layer (not the driver modules)
# avoids every driver having to import every other driver.
from instrument.drivers.agilent_33120a import Agilent33120ADriver
from instrument.drivers.generic_dmm import GenericDMMDriver
from instrument.drivers.u2702a import U2702ADriver

DRIVER_REGISTRY: dict[str, type] = {
    "U2702A": U2702ADriver,
    "Generic-DMM": GenericDMMDriver,
    "33120A": Agilent33120ADriver,
}


def auto_discover_port() -> Optional[str]:
    """Return the first CP2102N-ish serial port, or None if none found."""
    ports = list_serial_ports()
    return ports[0][0] if ports else None


class LabSession:
    """Context manager that owns a set of open instrument drivers.

    Use ``open(model)`` to add a driver; ``close()`` (or context exit)
    closes every driver in reverse order of open().
    """

    def __init__(self) -> None:
        self._drivers: list[InstrumentDriver] = []
        self._by_model: dict[str, InstrumentDriver] = {}

    def __enter__(self) -> "LabSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- Public API ---------------------------------------------------

    def discover(self) -> list[DiscoveredInstrument]:
        """Probe every connected serial port with ``*IDN?``.

        Returns a list of :class:`DiscoveredInstrument`. Matched
        instruments (model present in ``config.REGISTRY``) have
        ``.config`` set; unknown devices are still returned with their
        raw IDN reply so the user can see them.
        """
        return discover()

    def open(
        self,
        model: str,
        *,
        port: Optional[str] = None,
        demo: bool = False,
    ) -> InstrumentDriver:
        """Open a driver for ``model`` and return it.

        Args:
            model: registered model name (key in ``config.REGISTRY``).
            port: serial port to connect through; overrides auto-discovery.
            demo: if True, use a ``DemoBridge`` regardless of ``port``.

        Raises:
            KeyError: ``model`` isn't registered.
            RuntimeError: real bridge requested but no port available
                and ``demo`` wasn't set.
        """
        if model not in REGISTRY:
            raise KeyError(
                f"Unknown instrument model {model!r}; "
                f"registered: {list(REGISTRY)}",
            )
        if model not in DRIVER_REGISTRY:
            raise KeyError(
                f"No driver class for model {model!r}; "
                f"configs without drivers cannot be opened",
            )

        bridge = self._build_bridge(model, port=port, demo=demo)
        driver_cls = DRIVER_REGISTRY[model]
        driver = driver_cls(bridge)
        driver.open()
        self._drivers.append(driver)
        self._by_model[model] = driver
        logger.info("LabSession: opened %s via %s", model, type(bridge).__name__)
        return driver

    def get(self, model: str) -> InstrumentDriver:
        """Return an already-opened driver by model name."""
        return self._by_model[model]

    def close(self) -> None:
        """Close every open driver in LIFO order. Safe to call twice."""
        while self._drivers:
            drv = self._drivers.pop()
            try:
                drv.close()
            except Exception as e:
                logger.warning("Error closing %s: %s", type(drv).__name__, e)
        self._by_model.clear()

    @property
    def drivers(self) -> tuple[InstrumentDriver, ...]:
        return tuple(self._drivers)

    # -- Bridge factory ----------------------------------------------

    def _build_bridge(
        self,
        model: str,
        *,
        port: Optional[str],
        demo: bool,
    ) -> Bridge:
        cfg: InstrumentConfig = REGISTRY[model]

        if demo:
            # Pick the demo bridge that matches the instrument kind.
            # Scopes get synthetic waveforms; DMMs get synthetic
            # scalar readings; function generators store+echo setpoints.
            # Driver modules are bridge-agnostic — they just need the
            # protocol methods.
            if isinstance(cfg, DMMConfig):
                return DemoDMMBridge(model=model)
            if isinstance(cfg, FunctionGeneratorConfig):
                return DemoFuncGenBridge(model=model)
            return DemoBridge()

        chosen_port = port or auto_discover_port()
        if chosen_port is None:
            raise RuntimeError(
                f"No serial port available for {model}; "
                f"pass demo=True or port=... explicitly",
            )

        return SerialBridge(
            port=chosen_port,
            baudrate=cfg.serial.baudrate,
            timeout=cfg.serial.timeout_s,
        )
