"""
Automation-layer tests — LabSession + ActionRecorder.

Runs headless with DemoBridge. Proves scripts can open a driver, drive
it, record a session, save/load, and replay against a fresh driver.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation import ActionRecorder, LabSession
from automation.recorder import Action


class TestLabSession(unittest.TestCase):
    def test_open_demo_driver(self):
        with LabSession() as lab:
            scope = lab.open("U2702A", demo=True)
            self.assertIs(scope, lab.get("U2702A"))
            self.assertTrue(scope.bridge.is_open)
            self.assertEqual(len(lab.drivers), 1)

    def test_close_closes_all(self):
        lab = LabSession()
        scope = lab.open("U2702A", demo=True)
        lab.close()
        self.assertFalse(scope.bridge.is_open)
        self.assertEqual(len(lab.drivers), 0)

    def test_unknown_model_raises(self):
        with LabSession() as lab:
            with self.assertRaises(KeyError):
                lab.open("DOES_NOT_EXIST", demo=True)

    def test_script_drives_full_workflow(self):
        """Simulate an end-to-end headless script."""
        with LabSession() as lab:
            scope = lab.open("U2702A", demo=True)
            scope.apply_setting("channel.1.enabled", True)
            scope.apply_setting("channel.1.vdiv", 0.5)
            scope.apply_setting("timebase.tdiv", 1e-3)
            scope.apply_setting("trigger.level", 1.0)
            result = scope.acquire()
            self.assertGreaterEqual(len(result.waveforms), 1)
            wf = result.waveforms[0]
            # Measurements should be computable on the returned waveform.
            meas = wf.measurements
            self.assertIn("vpp", meas)

    def test_session_opens_dmm(self):
        """LabSession picks DemoDMMBridge for DMM-kind configs."""
        from instrument.demo_dmm_bridge import DemoDMMBridge
        from processing.acquisition_result import MeterReading
        with LabSession() as lab:
            dmm = lab.open("Generic-DMM", demo=True)
            self.assertIsInstance(dmm.bridge, DemoDMMBridge)
            reading = dmm.acquire()
            self.assertIsInstance(reading, MeterReading)

    def test_session_hosts_scope_and_dmm_simultaneously(self):
        """Prove the lab-bench case: two instruments in one session."""
        with LabSession() as lab:
            scope = lab.open("U2702A", demo=True)
            dmm = lab.open("Generic-DMM", demo=True)
            self.assertEqual(len(lab.drivers), 2)
            # Drive both — they must not interfere with each other's state.
            scope.apply_setting("channel.1.vdiv", 2.0)
            dmm.apply_setting("mode", "DCV")
            s_result = scope.acquire()
            d_reading = dmm.acquire()
            self.assertGreaterEqual(len(s_result.waveforms), 1)
            self.assertAlmostEqual(d_reading.primary, 3.3, delta=0.5)

    def test_session_hosts_scope_dmm_and_funcgen_simultaneously(self):
        """The full lab bench: three different instrument kinds in
        one process, each emitting its own AcquisitionResult shape.
        """
        from processing.acquisition_result import (
            GeneratorState, MeterReading,
        )
        from processing.waveform import WaveformData

        with LabSession() as lab:
            scope = lab.open("U2702A", demo=True)
            dmm = lab.open("Generic-DMM", demo=True)
            gen = lab.open("33120A", demo=True)
            self.assertEqual(len(lab.drivers), 3)

            # Drive each independently — settings on one must not
            # leak into another.
            scope.apply_setting("channel.1.vdiv", 1.0)
            dmm.apply_setting("mode", "DCV")
            gen.apply_setting("waveform", "TRI")
            gen.apply_setting("frequency", 500.0)
            gen.apply_setting("amplitude", 3.0)
            gen.apply_setting("output_enabled", True)

            s_result = scope.acquire()
            d_reading = dmm.acquire()
            g_state = gen.acquire()

            # Each driver emits its own result type.
            self.assertTrue(s_result.waveforms)
            self.assertIsInstance(s_result.waveforms[0], WaveformData)
            self.assertIsInstance(d_reading, MeterReading)
            self.assertIsInstance(g_state, GeneratorState)

            # Func-gen state roundtrips.
            self.assertTrue(g_state.output_enabled)
            self.assertEqual(g_state.setpoints["waveform"], "TRI")
            self.assertAlmostEqual(g_state.setpoints["frequency"], 500.0)
            self.assertAlmostEqual(g_state.setpoints["amplitude"], 3.0)

            # Settings on the func-gen didn't touch the scope or DMM.
            self.assertEqual(scope.read_setting("channel.1.vdiv"), 1.0)
            self.assertEqual(dmm.read_setting("mode"), "DCV")


class TestActionRecorder(unittest.TestCase):
    def _driver(self):
        lab = LabSession()
        self.addCleanup(lab.close)
        return lab.open("U2702A", demo=True)

    def test_records_only_when_started(self):
        rec = ActionRecorder(self._driver())
        rec.apply_setting("channel.1.vdiv", 0.5)
        self.assertEqual(len(rec.actions), 0)  # not recording yet
        rec.start()
        rec.apply_setting("channel.1.vdiv", 1.0)
        rec.stop()
        rec.apply_setting("channel.1.vdiv", 2.0)
        self.assertEqual(len(rec.actions), 1)
        self.assertEqual(rec.actions[0].args, ("channel.1.vdiv", 1.0))

    def test_save_load_roundtrip(self):
        rec = ActionRecorder(self._driver())
        rec.start()
        rec.apply_setting("channel.1.vdiv", 0.5)
        rec.apply_setting("trigger.level", 1.2)
        rec.acquire()
        rec.stop()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recording.json"
            rec.save(path)
            loaded = ActionRecorder.load(path)

        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].method, "apply_setting")
        self.assertEqual(loaded[0].args, ("channel.1.vdiv", 0.5))
        self.assertEqual(loaded[2].method, "acquire")

    def test_replay_against_fresh_driver(self):
        # Record against one driver, replay against another — proves
        # the recording is portable.
        rec = ActionRecorder(self._driver())
        rec.start()
        rec.apply_setting("channel.1.vdiv", 0.5)
        rec.apply_setting("trigger.level", 1.0)
        rec.acquire()
        rec.stop()

        with LabSession() as lab:
            fresh = lab.open("U2702A", demo=True)
            results = ActionRecorder.replay(fresh, list(rec.actions))

        # Two apply_setting (None) + one acquire (AcquireResult)
        self.assertEqual(len(results), 3)
        self.assertIsNone(results[0])
        self.assertIsNone(results[1])
        self.assertGreaterEqual(len(results[2].waveforms), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
