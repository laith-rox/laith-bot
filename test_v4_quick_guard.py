from datetime import datetime, timezone
import unittest

from v4_quick_guard import guard_alert_message, guard_quick_setup

UTC = timezone.utc


class V4QuickGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)

    def test_allows_weak_high_risk_setup_for_manual_decision(self):
        setup = {"side": "BUY", "score": 4, "risk_level": "مرتفعة"}
        result = guard_quick_setup(setup, [], self.now)
        self.assertTrue(result["allowed"])

    def test_allows_same_side_candidate_while_previous_is_active(self):
        setup = {"side": "SELL", "score": 5, "risk_level": "متوسطة"}
        rows = [{"id": "old", "status": "active", "side": "SELL"}]
        result = guard_quick_setup(setup, rows, self.now)
        self.assertTrue(result["allowed"])

    def test_opposite_side_active_does_not_block(self):
        setup = {"side": "SELL", "score": 5, "risk_level": "متوسطة"}
        rows = [{"id": "old", "status": "active", "side": "BUY"}]
        result = guard_quick_setup(setup, rows, self.now)
        self.assertTrue(result["allowed"])

    def test_two_recent_same_side_stops_trigger_fifteen_minute_cooldown(self):
        setup = {"side": "BUY", "score": 5, "risk_level": "متوسطة"}
        rows = [
            {"status": "closed", "side": "BUY", "outcome": "STOP", "closed": self.now.timestamp() - 600},
            {"status": "closed", "side": "BUY", "outcome": "STOP", "closed": self.now.timestamp() - 120},
        ]
        block = guard_quick_setup(setup, rows, self.now)
        self.assertFalse(block["allowed"])
        self.assertEqual(block["reason"], "stop_cooldown")
        self.assertGreater(block["remaining_seconds"], 0)
        self.assertIn("طوارئ V4", guard_alert_message(block))

    def test_cooldown_expires_after_fifteen_minutes(self):
        setup = {"side": "BUY", "score": 5, "risk_level": "متوسطة"}
        rows = [
            {"status": "closed", "side": "BUY", "outcome": "STOP", "closed": self.now.timestamp() - 1800},
            {"status": "closed", "side": "BUY", "outcome": "STOP", "closed": self.now.timestamp() - 901},
        ]
        result = guard_quick_setup(setup, rows, self.now)
        self.assertTrue(result["allowed"])

    def test_non_stop_breaks_same_side_stop_streak(self):
        setup = {"side": "BUY", "score": 5, "risk_level": "متوسطة"}
        rows = [
            {"status": "closed", "side": "BUY", "outcome": "STOP", "closed": self.now.timestamp() - 600},
            {"status": "closed", "side": "BUY", "outcome": "TARGET", "closed": self.now.timestamp() - 300},
            {"status": "closed", "side": "BUY", "outcome": "STOP", "closed": self.now.timestamp() - 120},
        ]
        result = guard_quick_setup(setup, rows, self.now)
        self.assertTrue(result["allowed"])


if __name__ == "__main__":
    unittest.main()
