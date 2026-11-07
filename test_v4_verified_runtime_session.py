"""Regression tests: verified broker schedule gates V4 polling."""
import unittest
from datetime import datetime, timedelta, timezone
from v4_runtime import verified_runtime_session_state

UTC = timezone.utc


class VerifiedRuntimeSessionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    def test_missing_calendar_fails_closed(self):
        self.assertEqual(verified_runtime_session_state(self.now, []),
                         "BROKER_CALENDAR_UNVERIFIED")

    def test_closed_weekend_and_preopen_are_not_open(self):
        sessions = [(self.now, self.now + timedelta(hours=4))]
        self.assertEqual(verified_runtime_session_state(self.now - timedelta(seconds=1), sessions),
                         "BROKER_SESSION_CLOSED")
        self.assertEqual(verified_runtime_session_state(self.now + timedelta(hours=4), sessions),
                         "BROKER_SESSION_CLOSED")

    def test_verified_open_window(self):
        sessions = [(self.now - timedelta(hours=1), self.now + timedelta(hours=1))]
        self.assertEqual(verified_runtime_session_state(self.now, sessions), "OPEN")

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            verified_runtime_session_state(self.now.replace(tzinfo=None), [])


if __name__ == "__main__":
    unittest.main()
