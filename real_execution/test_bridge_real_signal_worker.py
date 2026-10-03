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

    def test_sniper_live_stop_ladder_is_3_to_10(self):
        base = {
            "mode": "SNIPER",
            "side": "BUY",
            "checks": {"BUY": [False] * 7},
        }
        expected = {3: 3.0, 4: 3.0, 5: 5.0, 6: 7.0, 7: 10.0}
        for strength, budget in expected.items():
            signal = dict(base)
            checks = [True] * strength + [False] * (7 - strength)
            signal["checks"] = {"BUY": checks}
            self.assertEqual(worker.engine.sniper_budget_usd(signal), budget)

    def test_main_target_is_structure_adaptive(self):
        mtf = {
            "break_up": True,
            "retest_up": True,
            "h4_resistance": 103.0,
        }
        target = worker.engine.adaptive_main_target_r(
            "BUY", 100.0, 1.0, mtf, confidence=9
        )
        self.assertGreaterEqual(target, 2.0)
        self.assertLessEqual(target, 3.0)

        close_boundary = dict(mtf, h4_resistance=101.0)
        capped = worker.engine.adaptive_main_target_r(
            "BUY", 100.0, 1.0, close_boundary, confidence=9
        )
        self.assertLess(capped, target)

    def test_sniper_budget_uses_requested_tier_not_old_effective_budget(self):
        signal = {
            "mode": "SNIPER",
            "side": "BUY",
            "risk_distance": 4.5,
            "checks": {"BUY": [True, True, True, True, True, False, False]},
        }
        health = {
            "effective_risk_budget_usd": 3.0,
            "strong_risk_budget_usd": 15.0,
            "position_risk_usd": 0.0,
            "total_position_risk_usd": 0.0,
        }
        self.assertEqual(worker.engine.same_entry_copies(signal, health), 1)


    def test_reopen_gap_requires_three_closed_m5_bars(self):
        from datetime import datetime, timezone, timedelta
        start = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)
        rows = []
        for i in range(27):
            t = start + timedelta(minutes=5*i)
            rows.append({"datetime": t.isoformat(), "open": 1, "high": 2, "low": 0, "close": 1})
        # Simulate a daily/weekend closure, then only two completed M5 bars.
        reopen = start + timedelta(hours=10)
        for i in range(2):
            t = reopen + timedelta(minutes=5*i)
            rows.append({"datetime": t.isoformat(), "open": 1, "high": 2, "low": 0, "close": 1})
        self.assertEqual(worker.engine._rows_after_last_gap(rows, 5 * 60), 2)

    def test_native_h4_aggregation_is_forbidden(self):
        import multi_timeframe_structure as mtf
        with self.assertRaisesRegex(RuntimeError, "native_mt5_h4_required"):
            mtf.aggregate_h4([])


    def test_session_windows_are_fail_closed(self):
        # Bar timestamps are UTC; Palestine is UTC+3 in this strategy clock.
        main_ok = {"mode": "MAIN", "bar": "2026-10-03T01:30:00Z"}
        main_late = {"mode": "MAIN", "bar": "2026-10-03T04:00:00Z"}
        sniper_ok = {"mode": "SNIPER", "bar": "2026-10-03T16:00:00Z"}
        sniper_closed = {"mode": "SNIPER", "bar": "2026-10-03T10:00:00Z"}
        self.assertIsNone(worker.session_block_reason(main_ok))
        self.assertEqual(worker.session_block_reason(main_late), "main_session_closed")
        self.assertIsNone(worker.session_block_reason(sniper_ok))
        self.assertEqual(worker.session_block_reason(sniper_closed), "sniper_session_closed")

    def test_main_publish_requires_fresh_closed_h4_after_reopen(self):
        signal = {
            "side": "BUY",
            "bar": "2026-10-03T01:30:00Z",
            "mode": "MAIN",
            "risk_distance": 1.0,
            "target_r": 2.0,
            "checks": {"BUY": [True, True, True, True, True, False, False]},
            "native_h4_reopen_ready": False,
        }
        with self.assertRaisesRegex(RuntimeError, "main_native_h4_reopen_warmup"):
            worker.publish_signal(signal, spot_override=4100.0)

    def test_native_h4_reopen_waits_for_one_closed_h4(self):
        from datetime import datetime, timezone, timedelta
        base = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
        old = []
        for i in range(30):
            t = base + timedelta(hours=4*i)
            old.append({"datetime": t.isoformat(), "open": 1, "high": 2, "low": 0, "close": 1})
        reopen = old[-1]["datetime"]
        gap_start = datetime.fromisoformat(reopen) + timedelta(hours=52)
        only_active = old + [{
            "datetime": gap_start.isoformat(), "open": 1, "high": 2, "low": 0, "close": 1
        }]
        self.assertFalse(worker.engine.native_h4_reopen_ready(only_active))
        one_closed_plus_active = only_active + [{
            "datetime": (gap_start + timedelta(hours=4)).isoformat(),
            "open": 1, "high": 2, "low": 0, "close": 1
        }]
        self.assertTrue(worker.engine.native_h4_reopen_ready(one_closed_plus_active))



if __name__ == "__main__":
    unittest.main()
