"""Independent V4 safety monitor cannot bypass verified broker calendar."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from v4_runtime import verified_safety_market_closed


class VerifiedMinuteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        self.sessions = [(self.now - timedelta(hours=1), self.now + timedelta(hours=1))]

    def test_missing_calendar_fails_closed(self):
        with patch("v4_runtime.trading_guard_closed", return_value=False):
            self.assertTrue(verified_safety_market_closed(self.now, []))

    def test_outside_broker_session_fails_closed(self):
        with patch("v4_runtime.trading_guard_closed", return_value=False):
            self.assertTrue(verified_safety_market_closed(self.now + timedelta(hours=2), self.sessions))

    def test_inside_verified_session_can_monitor(self):
        with patch("v4_runtime.trading_guard_closed", return_value=False):
            self.assertFalse(verified_safety_market_closed(self.now, self.sessions))

    def test_weekend_or_market_guard_overrides_calendar(self):
        with patch("v4_runtime.trading_guard_closed", return_value=True):
            self.assertTrue(verified_safety_market_closed(self.now, self.sessions))


if __name__ == "__main__":
    unittest.main()
