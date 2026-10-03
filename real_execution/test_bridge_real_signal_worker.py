import os
import unittest

os.environ["REAL_SIGNAL_ENABLED"] = "false"
os.environ["REAL_LIVE_HANDOFF_ENABLED"] = "false"
os.environ["REAL_VOLUME"] = "0"
os.environ["REAL_MAX_PUBLISH_PER_HOUR"] = "0"
os.environ.pop("REAL_BRIDGE_URL", None)
os.environ.pop("REAL_BRIDGE_PUBLISH_TOKEN", None)

import bridge_real_signal_worker as worker


class StopDisabledLoop(Exception):
    pass


class RealSignalMirrorTests(unittest.TestCase):
    def test_defaults_are_disabled(self):
        self.assertFalse(worker.REAL_SIGNAL_ENABLED)
        self.assertFalse(worker.REAL_LIVE_HANDOFF_ENABLED)
        self.assertEqual(worker.VOLUME, 0.0)
        self.assertEqual(worker.MAX_PUBLISH_PER_HOUR, 0)
        self.assertEqual(worker.config_reason(), "real_signal_disabled")

    def test_disabled_worker_never_contacts_bridge(self):
        original_sleep = worker.time.sleep
        original_health = worker.bridge_health

        def stop_sleep(_seconds):
            raise StopDisabledLoop()

        def forbidden_health():
            raise AssertionError("disabled REAL worker must not contact bridge")

        worker.time.sleep = stop_sleep
        worker.bridge_health = forbidden_health
        try:
            with self.assertRaises(StopDisabledLoop):
                worker.run_forever()
        finally:
            worker.time.sleep = original_sleep
            worker.bridge_health = original_health

    def test_real_publish_keeps_demo_lot_and_checks(self):
        original_request = worker.engine._json_request
        original_volume = worker.VOLUME
        original_token = worker.PUBLISH_TOKEN
        captured = {}

        def fake_request(url, method="GET", payload=None, headers=None, timeout=10):
            captured["url"] = url
            captured["method"] = method
            captured["payload"] = payload
            captured["headers"] = headers
            return 201, {"ok": True}

        worker.engine._json_request = fake_request
        worker.VOLUME = 0.01
        worker.PUBLISH_TOKEN = "test-publish-token"
        try:
            signal = {
                "side": "BUY",
                "bar": "2026-10-02 16:35:00",
                "mode": "SNIPER",
                "risk_distance": 1.0,
                "target_r": 1.25,
                "checks": {"BUY": [True, True, True, True, True, False, False]},
            }
            status, response, _key = worker.publish_signal(signal, spot_override=4100.0)
            self.assertEqual(status, 201)
            self.assertTrue(response["ok"])
            self.assertEqual(captured["payload"]["mode"], "REAL")
            self.assertEqual(captured["payload"]["volume"], 0.01)
            self.assertEqual(len(captured["payload"]["checks"]["BUY"]), 7)
            self.assertFalse(captured["payload"]["forced"])
        finally:
            worker.engine._json_request = original_request
            worker.VOLUME = original_volume
            worker.PUBLISH_TOKEN = original_token

    def test_full_demo_strategy_functions_are_present(self):
        for name in (
            "compute_signal",
            "apply_main_structure",
            "recover_m15_continuation",
            "recover_strong_structural_entry",
            "sniper_chase_block_reason",
            "same_entry_copies",
        ):
            self.assertTrue(callable(getattr(worker.engine, name, None)), name)


if __name__ == "__main__":
    unittest.main()
