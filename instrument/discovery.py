"""
Instrument discovery — probe serial ports with ``*IDN?`` and match
against the config registry.

SCPI-compliant instruments respond to ``*IDN?`` with a comma-separated
string ``manufacturer,model,serial,firmware``. We parse that, look up
the model in ``config.REGISTRY``, and return a list of ports with their
detected instruments. Unrecognised devices are still reported with
their raw IDN so the user can see *something* is there.

Used by:
  - ``ConnectionDialog``: "Scan" button populates the device dropdown.
  - ``automation.LabSession.discover()``: headless enumeration.

The U2702A's firmware-update mode (PID 0x2818) doesn't answer
``*IDN?``, so discovery can't see a scope that hasn't been booted
into operational mode yet. That's a hardware limitation; the boot
sequence runs on the ESP32 before the port becomes queryable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from config import REGISTRY, InstrumentConfig
from instrument.serial_bridge import (
    SerialBridge,
    SerialBridgeError,
    list_serial_ports,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredInstrument:
    """One instrument found by probing a serial port."""

    port: str
    port_description: str
    raw_idn: Optional[str]                 # None if the port didn't answer
    vendor: Optional[str]
    model: Optional[str]
    serial: Optional[str]
    firmware: Optional[str]
    config: Optional[InstrumentConfig]     # None if model isn't in REGISTRY

    @property
    def display_name(self) -> str:
        """Pretty name for menus / dialog lists."""
        if self.config is not None:
            return f"{self.config.display_name}  [{self.port}]"
        if self.model:
            vendor = self.vendor or "Unknown"
            return f"{vendor} {self.model}  [{self.port}] (unregistered)"
        return f"{self.port_description}"

    @property
    def is_matched(self) -> bool:
        return self.config is not None


def parse_idn(raw: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Parse a ``*IDN?`` response into (vendor, model, serial, firmware).

    Accepts the SCPI standard comma-separated form. Missing fields are
    returned as None. Extra trailing fields are ignored.
    """
    if not raw:
        return None, None, None, None
    parts = [p.strip() for p in raw.strip().split(",")]
    while len(parts) < 4:
        parts.append("")
    vendor, model, serial, firmware = parts[:4]
    return (
        vendor or None,
        model or None,
        serial or None,
        firmware or None,
    )


def _match_registry(model: Optional[str]) -> Optional[InstrumentConfig]:
    """Look up an instrument config by model name, case-insensitive."""
    if not model:
        return None
    # Exact match first.
    if model in REGISTRY:
        return REGISTRY[model]
    # Case-insensitive fallback — SCPI IDNs vary in case.
    upper = model.upper()
    for key, cfg in REGISTRY.items():
        if key.upper() == upper:
            return cfg
    return None


def probe_port(
    port: str,
    *,
    baudrate: int = 2_000_000,
    timeout: float = 1.5,
    open_timeout: float = 3.0,
) -> Optional[str]:
    """Open ``port`` briefly and send ``*IDN?``; return the raw reply.

    Returns ``None`` if the port didn't respond or couldn't be opened.
    Never raises — probing a port must be safe to do against unknown
    hardware.

    ``open_timeout`` is how long we wait for the ESP32 bridge to
    finish booting / reach READY status before giving up; ``timeout``
    is the per-query SCPI timeout after that.
    """
    bridge = SerialBridge(port=port, baudrate=baudrate, timeout=timeout)
    try:
        bridge.open()
    except Exception as e:
        logger.debug("probe_port(%s): open failed: %s", port, e)
        return None

    try:
        # Wait for the bridge to say it's ready before querying —
        # otherwise the *IDN? goes out before the ESP32 has the
        # USB host up and we get a timeout.
        try:
            bridge.wait_for_status("READY", timeout=open_timeout)
        except Exception:
            # Not a fatal error — some bridges go READY silently.
            pass

        try:
            reply = bridge.query("*IDN?", timeout=timeout)
            return reply.strip() or None
        except (SerialBridgeError, Exception) as e:
            logger.debug("probe_port(%s): *IDN? failed: %s", port, e)
            return None
    finally:
        try:
            bridge.close()
        except Exception:
            pass


def discover(*, include_unresponsive: bool = False) -> list[DiscoveredInstrument]:
    """Probe every CP2102N-ish serial port and return what's there.

    Args:
        include_unresponsive: if True, ports that didn't respond to
            ``*IDN?`` are still included (with raw_idn=None) so the
            user can pick them manually. Default: only include ports
            that answered.

    Returns:
        List of :class:`DiscoveredInstrument`, in port-enumeration order.
    """
    results: list[DiscoveredInstrument] = []
    for port, description in list_serial_ports():
        raw = probe_port(port)
        vendor, model, serial, firmware = parse_idn(raw) if raw else (None,) * 4
        cfg = _match_registry(model)

        if raw is None and not include_unresponsive:
            continue

        results.append(DiscoveredInstrument(
            port=port,
            port_description=description,
            raw_idn=raw,
            vendor=vendor,
            model=model,
            serial=serial,
            firmware=firmware,
            config=cfg,
        ))
    return results
