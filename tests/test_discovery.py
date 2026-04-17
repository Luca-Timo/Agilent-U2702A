"""
Discovery-layer tests.

These don't touch real hardware — they focus on the pure logic:
parse_idn() correctness and registry matching.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from instrument.discovery import (
    DiscoveredInstrument,
    parse_idn,
    _match_registry,
)
from config import REGISTRY


class TestParseIdn(unittest.TestCase):
    def test_standard_scpi_idn(self):
        vendor, model, serial, firmware = parse_idn(
            "Agilent Technologies,U2702A,TW56001234,1.00"
        )
        self.assertEqual(vendor, "Agilent Technologies")
        self.assertEqual(model, "U2702A")
        self.assertEqual(serial, "TW56001234")
        self.assertEqual(firmware, "1.00")

    def test_keysight_long_firmware(self):
        _, model, _, firmware = parse_idn(
            "Keysight Technologies,34461A,MY56021234,A.01.12-02.36-02.36-00.52-01-01"
        )
        self.assertEqual(model, "34461A")
        self.assertTrue(firmware.startswith("A.01"))

    def test_whitespace_tolerance(self):
        v, m, s, f = parse_idn(
            "  RIGOL TECHNOLOGIES , DG4162 , DG4E160400131 , 00.02.08.SP5  \r\n"
        )
        self.assertEqual(v, "RIGOL TECHNOLOGIES")
        self.assertEqual(m, "DG4162")
        self.assertEqual(s, "DG4E160400131")
        self.assertEqual(f, "00.02.08.SP5")

    def test_missing_fields_become_none(self):
        v, m, s, f = parse_idn("Vendor,Model")
        self.assertEqual(v, "Vendor")
        self.assertEqual(m, "Model")
        self.assertIsNone(s)
        self.assertIsNone(f)

    def test_empty_input_returns_all_none(self):
        self.assertEqual(parse_idn(""), (None, None, None, None))
        self.assertEqual(parse_idn("   "), (None, None, None, None))


class TestRegistryMatching(unittest.TestCase):
    def test_exact_match(self):
        cfg = _match_registry("U2702A")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.model, "U2702A")

    def test_case_insensitive_match(self):
        cfg = _match_registry("u2702a")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.model, "U2702A")

    def test_no_match(self):
        self.assertIsNone(_match_registry("NOT_A_REAL_MODEL"))

    def test_empty_model(self):
        self.assertIsNone(_match_registry(""))
        self.assertIsNone(_match_registry(None))


class TestDiscoveredInstrumentDisplay(unittest.TestCase):
    def test_matched_uses_config_display_name(self):
        cfg = REGISTRY["U2702A"]
        d = DiscoveredInstrument(
            port="/dev/cu.usbserial-110",
            port_description="CP2102N",
            raw_idn="Agilent Technologies,U2702A,X,Y",
            vendor="Agilent Technologies",
            model="U2702A",
            serial="X",
            firmware="Y",
            config=cfg,
        )
        self.assertTrue(d.is_matched)
        self.assertIn("Agilent U2702A", d.display_name)
        self.assertIn("/dev/cu.usbserial-110", d.display_name)

    def test_unmatched_labelled_unregistered(self):
        d = DiscoveredInstrument(
            port="/dev/cu.usbserial-210",
            port_description="CP2102N",
            raw_idn="Foo,BAR123,Z,W",
            vendor="Foo",
            model="BAR123",
            serial="Z",
            firmware="W",
            config=None,
        )
        self.assertFalse(d.is_matched)
        self.assertIn("unregistered", d.display_name)


class TestAppSettingsToggle(unittest.TestCase):
    def test_auto_discovery_flag_default_true(self):
        from gui.app_settings import SETTINGS
        self.assertTrue(SETTINGS.auto_discovery_enabled)

    def test_auto_discovery_flag_roundtrip(self):
        from gui.app_settings import SETTINGS
        original = SETTINGS.auto_discovery_enabled
        try:
            SETTINGS.auto_discovery_enabled = False
            self.assertFalse(SETTINGS.auto_discovery_enabled)
            SETTINGS.auto_discovery_enabled = True
            self.assertTrue(SETTINGS.auto_discovery_enabled)
        finally:
            SETTINGS.auto_discovery_enabled = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
