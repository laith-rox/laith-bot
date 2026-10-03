import importlib.util
import os
import unittest

os.environ["REAL_BRIDGE_ARMED"] = "false"
os.environ["REAL_EXECUTION_ENABLED"] = "false"
os.environ["REAL_FIXED_VOLUME"] = "0"
for k in ("REAL_BRIDGE_CLIENT_TOKEN","REAL_BRIDGE_PUBLISH_TOKEN","REAL_BRIDGE_HMAC_SECRET"):
    os.environ.pop(k, None)

spec = importlib.util.spec_from_file_location("bridge_real_api_under_test", "bridge_real_api.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class RealBridgeFailClosedTests(unittest.TestCase):
    def setUp(self):
        bridge.REAL_ARMED = False
        bridge.EXECUTION_ENABLED = False
        bridge.FIXED_VOLUME = 0.0
        bridge._client_state = None
        bridge._market_state = None
        bridge._client_last_poll = None
        bridge._emergency_stop = True

    def test_status_is_not_ready_by_default(self):
        s = bridge._status()
        self.assertFalse(s["armed"])
        self.assertFalse(s["execution_enabled"])
        self.assertFalse(s["configured"])
        self.assertFalse(s["ready"])

    def test_publish_rejected_when_disarmed(self):
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_not_armed")

    def test_execution_switch_is_independent(self):
        bridge.REAL_ARMED = True
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_execution_disabled")

    def test_volume_must_be_explicitly_configured(self):
        bridge.REAL_ARMED = True
        bridge.EXECUTION_ENABLED = True
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_volume_not_configured")

    def _market_payload(self, source_timestamp):
        rows = [{"datetime": "2026.10.03 00:00:00"} for _ in range(30)]
        return {
            "source_timestamp": source_timestamp,
            "tick_timestamp": 1_999_999_995,
            "source_clock": "UTC_EPOCH",
            "h4_source": "MT5_NATIVE_TIMEFRAME_H4",
            "m5": list(rows),
            "m15": list(rows),
            "h1": list(rows),
            "h4": list(rows),
        }

    def test_fresh_market_source_is_accepted(self):
        now = 2_000_000_000
        ok, reason = bridge._validate_market_payload(
            self._market_payload(now - 60), now=now
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "approved")

    def test_stale_market_source_is_rejected(self):
        now = 2_000_000_000
        ok, reason = bridge._validate_market_payload(
            self._market_payload(now - bridge.MARKET_SOURCE_FRESH_SECONDS - 1),
            now=now,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "market_source_stale")

    def test_stale_tick_is_rejected_quickly(self):
        payload = self._market_payload(1_999_999_990)
        payload["tick_timestamp"] = 2_000_000_000 - bridge.MARKET_TICK_FRESH_SECONDS - 1
        ok, reason = bridge._validate_market_payload(payload, now=2_000_000_000)
        self.assertFalse(ok)
        self.assertEqual(reason, "market_tick_stale")

    def test_tick_timestamp_is_required(self):
        payload = self._market_payload(1_999_999_990)
        payload.pop("tick_timestamp")
        ok, reason = bridge._validate_market_payload(payload, now=2_000_000_000)
        self.assertFalse(ok)
        self.assertEqual(reason, "market_tick_timestamp_required")


    def test_market_source_timestamp_is_required(self):
        payload = self._market_payload(1_999_999_940)
        payload.pop("source_timestamp")
        ok, reason = bridge._validate_market_payload(payload, now=2_000_000_000)
        self.assertFalse(ok)
        self.assertEqual(reason, "market_source_timestamp_required")

    def test_market_rejects_non_native_h4(self):
        payload = self._market_payload(1_999_999_940)
        payload["h4_source"] = "AGGREGATED_H1"
        ok, reason = bridge._validate_market_payload(payload, now=2_000_000_000)
        self.assertFalse(ok)
        self.assertEqual(reason, "native_h4_required")

    def test_market_requires_utc_epoch_clock(self):
        payload = self._market_payload(1_999_999_940)
        payload["source_clock"] = "LOCALTIME"
        ok, reason = bridge._validate_market_payload(payload, now=2_000_000_000)
        self.assertFalse(ok)
        self.assertEqual(reason, "utc_source_clock_required")


    def test_preflight_lists_fail_closed_blockers(self):
        bridge.REAL_ARMED = False
        bridge.EXECUTION_ENABLED = False
        bridge.FIXED_VOLUME = 0.0
        bridge._emergency_stop = True
        bridge._client_state = None
        bridge._market_state = None
        blockers = bridge._readiness_blockers(now=2_000_000_000)
        self.assertIn("risk_unset", blockers)
        self.assertIn("not_armed", blockers)
        self.assertIn("execution_disabled", blockers)
        self.assertIn("emergency_stop", blockers)
        self.assertIn("mt5_state_stale", blockers)
        self.assertIn("market_closed_or_stale", blockers)

    def test_status_reports_preflight_false_while_locked(self):
        bridge.REAL_ARMED = False
        bridge.EXECUTION_ENABLED = False
        bridge.FIXED_VOLUME = 0.0
        bridge._emergency_stop = True
        s = bridge._status()
        self.assertFalse(s["preflight_ok"])
        self.assertTrue(isinstance(s["readiness_blockers"], list))

    def test_restart_is_emergency_latched(self):
        self.assertTrue(bridge._restart_latched)
        self.assertTrue(bridge._emergency_stop)
        self.assertTrue(bridge._status()["restart_latched"])


    def test_fresh_state_with_autotrading_off_is_not_ready(self):
        now = 2_000_000_000
        bridge._client_state = {
            "received_at": now - 1,
            "terminal_trade_allowed": False,
        }
        blockers = bridge._readiness_blockers(now=now)
        self.assertIn("terminal_autotrading_off", blockers)

    def test_status_exposes_terminal_and_spread_metadata(self):
        now = 2_000_000_000
        bridge._client_state = {
            "received_at": now - 1,
            "terminal_trade_allowed": False,
            "account_trade_allowed": True,
            "account_trade_expert": True,
            "bid": 4200.10,
            "ask": 4200.45,
            "spread_usd": 0.35,
            "tick_age_seconds": 1.2,
        }
        s = bridge._status()
        self.assertFalse(s["terminal_trade_allowed"])
        self.assertAlmostEqual(s["spread_usd"], 0.35)
        self.assertTrue(s["account_trade_allowed"])



if __name__ == "__main__":
    unittest.main()
