"""
Headless driver contract tests.

Runs with no QApplication and no real hardware — only the DemoBridge.
Every concrete InstrumentDriver implementation must pass these tests.
They're the regression guard for the "scripts and GUI call the same
code" invariant: if a driver method starts importing from ``gui/`` or
requires a Qt event loop, these tests will fail.

Run with:
    python3 -m pytest tests/test_driver_headless.py -v

Or standalone (no pytest needed):
    python3 tests/test_driver_headless.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Make repo root importable when run standalone.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from instrument.capabilities import (
    Capabilities,
    InstrumentKind,
    AcquisitionModel,
    OSCILLOSCOPE_DEFAULTS,
    DMM_DEFAULTS,
    FUNCGEN_DEFAULTS,
)
from instrument.driver import Bridge, InstrumentDriver
from instrument.demo_bridge import DemoBridge
from instrument.serial_bridge import SerialBridge


class TestBridgeProtocol(unittest.TestCase):
    """The Bridge protocol must be honoured by every transport."""

    def test_demo_bridge_conforms(self):
        b = DemoBridge()
        self.assertIsInstance(b, Bridge)

    def test_serial_bridge_conforms_structurally(self):
        # We can't instantiate SerialBridge without a port, but its
        # class must expose every Bridge method on the class body.
        # Instance-only attributes (``port`` is assigned in __init__)
        # are checked by constructing an instance.
        for method in ("open", "close", "write", "query", "query_binary",
                       "wait_for_status"):
            self.assertTrue(
                hasattr(SerialBridge, method),
                f"SerialBridge missing method {method!r}",
            )
        # Construct with a dummy port so __init__ runs; don't call open().
        b = SerialBridge(port="/dev/null")
        for attr in ("is_open", "bridge_status", "port"):
            self.assertTrue(
                hasattr(b, attr),
                f"SerialBridge instance missing attribute {attr!r}",
            )


class TestCapabilities(unittest.TestCase):
    """Capability presets must be internally consistent."""

    def test_scope_defaults(self):
        caps = OSCILLOSCOPE_DEFAULTS
        self.assertEqual(caps.kind, InstrumentKind.OSCILLOSCOPE)
        self.assertEqual(caps.acquisition_model, AcquisitionModel.WAVEFORM)
        self.assertTrue(caps.has_trigger)
        self.assertTrue(caps.has_measurements)
        self.assertIn("Vpp", caps.supported_measurements)

    def test_dmm_defaults(self):
        caps = DMM_DEFAULTS
        self.assertEqual(caps.kind, InstrumentKind.DMM)
        self.assertEqual(caps.acquisition_model, AcquisitionModel.SCALAR)
        self.assertFalse(caps.has_trigger)
        self.assertFalse(caps.has_measurements)

    def test_funcgen_defaults(self):
        caps = FUNCGEN_DEFAULTS
        self.assertEqual(caps.kind, InstrumentKind.FUNCTION_GENERATOR)
        self.assertEqual(caps.acquisition_model, AcquisitionModel.SETPOINT)
        self.assertTrue(caps.has_output_enable)

    def test_capabilities_are_immutable(self):
        with self.assertRaises((AttributeError, Exception)):
            OSCILLOSCOPE_DEFAULTS.num_channels = 4  # type: ignore[misc]


class DriverContractMixin:
    """Mixin that runs the InstrumentDriver contract against a driver
    instance. Subclasses provide ``build_driver()`` returning an
    unopened driver wired to a DemoBridge.

    The contract: every public method on the InstrumentDriver protocol
    can be called headless with no Qt in the process. Methods that
    aren't yet implemented must raise NotImplementedError, not succeed
    silently — silent no-ops mask regressions.
    """

    driver_class = None  # set by subclasses

    def build_driver(self) -> InstrumentDriver:
        raise NotImplementedError

    def test_driver_conforms_to_protocol(self):
        drv = self.build_driver()
        self.assertIsInstance(drv, InstrumentDriver)

    def test_has_capabilities(self):
        drv = self.build_driver()
        self.assertIsInstance(drv.capabilities, Capabilities)

    def test_open_close_roundtrip(self):
        drv = self.build_driver()
        drv.open()
        try:
            self.assertTrue(drv.bridge.is_open)
        finally:
            drv.close()
        self.assertFalse(drv.bridge.is_open)

    def test_init_sequence_returns_dict(self):
        drv = self.build_driver()
        drv.open()
        try:
            state = drv.init_sequence()
            self.assertIsInstance(state, dict)
        finally:
            drv.close()

    def test_supported_settings_returns_tuple(self):
        drv = self.build_driver()
        keys = drv.supported_settings()
        self.assertIsInstance(keys, tuple)
        # Every key must be a string; empty tuple is legal (no settings).
        self.assertTrue(all(isinstance(k, str) for k in keys))

    def test_no_gui_import(self):
        """The driver module must not import anything from gui/.

        Scripts must be able to use drivers without PySide6 widgets
        being loaded. The worker thread wraps drivers for the GUI; the
        dependency must not point the other way.
        """
        import inspect
        module = inspect.getmodule(self.driver_class)
        if module is None:
            self.skipTest("driver_class not bound to a module")
        src = inspect.getsource(module)
        for bad in ("from gui", "import gui."):
            self.assertNotIn(
                bad, src,
                f"{module.__name__} must not import from gui/ "
                f"(found {bad!r}); drivers run headless.",
            )


class TestU2702ADriver(DriverContractMixin, unittest.TestCase):
    """Contract suite for the Agilent U2702A driver."""

    from instrument.drivers.u2702a import U2702ADriver  # noqa: E402
    driver_class = U2702ADriver

    def build_driver(self):
        return self.driver_class(DemoBridge())

    def test_acquire_returns_waveforms(self):
        drv = self.build_driver()
        drv.open()
        try:
            result = drv.acquire()
            self.assertGreaterEqual(len(result.waveforms), 1)
            wf = result.waveforms[0]
            self.assertEqual(wf.voltage.shape, wf.time_axis.shape)
        finally:
            drv.close()

    def test_apply_setting_roundtrip(self):
        drv = self.build_driver()
        drv.open()
        try:
            drv.apply_setting("channel.1.vdiv", 0.5)
            drv.apply_setting("trigger.level", 1.23)
            drv.apply_setting("timebase.tdiv", 1e-4)
            self.assertEqual(drv.read_setting("channel.1.vdiv"), 0.5)
            self.assertAlmostEqual(drv.read_setting("trigger.level"), 1.23)
            self.assertAlmostEqual(drv.read_setting("timebase.tdiv"), 1e-4)
        finally:
            drv.close()

    def test_unknown_setting_raises(self):
        drv = self.build_driver()
        with self.assertRaises(KeyError):
            drv.apply_setting("nonsense.key", 42)

    def test_supported_settings_includes_channel_keys(self):
        drv = self.build_driver()
        keys = drv.supported_settings()
        self.assertIn("channel.1.vdiv", keys)
        self.assertIn("timebase.tdiv", keys)
        self.assertIn("trigger.level", keys)
        # Pulse-width trigger wiring
        self.assertIn("trigger.mode", keys)
        self.assertIn("trigger.pulse.polarity", keys)
        self.assertIn("trigger.pulse.qualifier", keys)
        self.assertIn("trigger.pulse.greater", keys)
        self.assertIn("trigger.pulse.less", keys)

    def test_pulse_width_trigger_apply_setting(self):
        """Pulse-width keys dispatch to the right bridge commands."""
        drv = self.build_driver()
        drv.open()
        try:
            drv.apply_setting("trigger.mode", "GLITCH")
            drv.apply_setting("trigger.pulse.polarity", "POS")
            drv.apply_setting("trigger.pulse.qualifier", "GRE")
            drv.apply_setting("trigger.pulse.greater", 1e-4)
            drv.apply_setting("trigger.pulse.less", 5e-6)
            # No roundtrip here — the demo bridge echoes writes but
            # the driver doesn't cache pulse-width state (it's
            # scope-side). This test just proves the commands
            # dispatch without raising.
        finally:
            drv.close()


class TestGenericDMMDriver(DriverContractMixin, unittest.TestCase):
    """Contract suite for the Generic SCPI DMM driver."""

    from instrument.drivers.generic_dmm import GenericDMMDriver  # noqa: E402
    from instrument.demo_dmm_bridge import DemoDMMBridge          # noqa: E402
    driver_class = GenericDMMDriver
    _demo_bridge_class = DemoDMMBridge

    def build_driver(self):
        return self.driver_class(self._demo_bridge_class())

    def test_acquire_returns_meter_reading(self):
        from processing.acquisition_result import MeterReading
        drv = self.build_driver()
        drv.open()
        try:
            reading = drv.acquire()
            self.assertIsInstance(reading, MeterReading)
            self.assertEqual(reading.kind, "scalar")
            self.assertEqual(reading.unit, "V")       # default mode is DCV
            # Nominal 3.3V ± drift/noise; give a wide band.
            self.assertAlmostEqual(reading.primary, 3.3, delta=0.5)
        finally:
            drv.close()

    def test_min_max_avg_track_across_reads(self):
        drv = self.build_driver()
        drv.open()
        try:
            for _ in range(5):
                r = drv.acquire()
            self.assertEqual(r.samples, 5)
            self.assertGreaterEqual(r.maximum, r.minimum)
            self.assertTrue(r.minimum <= r.average <= r.maximum)
        finally:
            drv.close()

    def test_mode_switch_resets_stats(self):
        drv = self.build_driver()
        drv.open()
        try:
            for _ in range(3):
                drv.acquire()
            r_before = drv.acquire()
            self.assertGreaterEqual(r_before.samples, 4)
            drv.apply_setting("mode", "ACV")
            r_after = drv.acquire()
            self.assertEqual(r_after.samples, 1)
            self.assertEqual(r_after.unit, "V")
        finally:
            drv.close()

    def test_unknown_mode_rejected(self):
        drv = self.build_driver()
        with self.assertRaises(KeyError):
            drv.apply_setting("mode", "NOT_A_REAL_MODE")

    def test_hold_returns_none(self):
        drv = self.build_driver()
        drv.open()
        try:
            first = drv.acquire()
            self.assertIsNotNone(first)
            drv.apply_setting("hold", True)
            self.assertIsNone(drv.acquire())
            drv.apply_setting("hold", False)
            self.assertIsNotNone(drv.acquire())
        finally:
            drv.close()


class TestAgilent33120ADriver(DriverContractMixin, unittest.TestCase):
    """Contract suite for the Agilent 33120A function generator driver."""

    from instrument.drivers.agilent_33120a import Agilent33120ADriver  # noqa: E402
    from instrument.demo_funcgen_bridge import DemoFuncGenBridge        # noqa: E402
    driver_class = Agilent33120ADriver
    _demo_bridge_class = DemoFuncGenBridge

    def build_driver(self):
        return self.driver_class(self._demo_bridge_class())

    def test_acquire_returns_generator_state(self):
        from processing.acquisition_result import GeneratorState
        drv = self.build_driver()
        drv.open()
        try:
            state = drv.acquire()
            self.assertIsInstance(state, GeneratorState)
            self.assertEqual(state.kind, "setpoint")
            for key in ("frequency", "amplitude", "offset",
                        "waveform", "output_load"):
                self.assertIn(key, state.setpoints)
        finally:
            drv.close()

    def test_output_off_on_open(self):
        """Safety invariant — open() must leave the output OFF
        regardless of what the instrument's previous state was."""
        bridge = self._demo_bridge_class()
        # Pre-set the demo bridge as if the instrument were left on.
        bridge.open()
        bridge.write("OUTP ON")
        bridge.close()
        # Now open the driver — it must force output off.
        drv = self.driver_class(bridge)
        drv.open()
        try:
            state = drv.acquire()
            self.assertFalse(
                state.output_enabled,
                "Driver.open() must force OUTP OFF for safety",
            )
        finally:
            drv.close()

    def test_apply_setting_roundtrip(self):
        drv = self.build_driver()
        drv.open()
        try:
            drv.apply_setting("frequency", 12345.0)
            drv.apply_setting("amplitude", 2.5)
            drv.apply_setting("offset", -0.5)
            drv.apply_setting("waveform", "TRI")
            drv.apply_setting("output_enabled", True)
            drv.apply_setting("output_load", "INF")
            self.assertAlmostEqual(drv.read_setting("frequency"), 12345.0)
            self.assertAlmostEqual(drv.read_setting("amplitude"), 2.5)
            self.assertAlmostEqual(drv.read_setting("offset"), -0.5)
            self.assertEqual(drv.read_setting("waveform"), "TRI")
            self.assertTrue(drv.read_setting("output_enabled"))
            self.assertEqual(drv.read_setting("output_load"), "INF")
        finally:
            drv.close()

    def test_frequency_out_of_range_rejected(self):
        drv = self.build_driver()
        drv.open()
        try:
            with self.assertRaises(ValueError):
                drv.apply_setting("frequency", -1.0)
            with self.assertRaises(ValueError):
                drv.apply_setting("frequency", 20_000_000.0)  # above 15 MHz
        finally:
            drv.close()

    def test_unknown_waveform_rejected(self):
        drv = self.build_driver()
        drv.open()
        try:
            with self.assertRaises(KeyError):
                drv.apply_setting("waveform", "BOGUS")
        finally:
            drv.close()

    def test_duty_cycle_rejected_on_non_square(self):
        """PULS:DCYC is only valid when FUNC:SHAP SQU."""
        drv = self.build_driver()
        drv.open()
        try:
            # Default waveform is SIN — duty cycle should fail.
            drv.apply_setting("waveform", "SIN")
            with self.assertRaises(ValueError):
                drv.apply_setting("duty_cycle", 50)
            # Switch to SQU, now it should work.
            drv.apply_setting("waveform", "SQU")
            drv.apply_setting("duty_cycle", 30)
            self.assertAlmostEqual(drv.read_setting("duty_cycle"), 30.0)
        finally:
            drv.close()

    def test_unknown_setting_rejected(self):
        drv = self.build_driver()
        with self.assertRaises(KeyError):
            drv.apply_setting("not_a_real_key", 42)


if __name__ == "__main__":
    unittest.main(verbosity=2)
