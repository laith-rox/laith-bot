"""Regression: experimental gold cannot trade on unverified broker/news calendars.

Only standard-library unittest; never makes a network request or broker order.
"""
import json
import unittest
from datetime import datetime, timezone

from v4_verified_calendar import (
    verified_sessions,
    verified_news_calendar_available,
    verified_entry_calendar_available,
)
from v4_runtime import verified_runtime_session_state


class ExperimentalGoldCalendarGateTests(unittest.TestCase):
    def test_missing_calendar_fails_closed(self):
        self.assertFalse(verified_entry_calendar_available(None))
        self.assertFalse(verified_news_calendar_available(None))
        self.assertEqual(
            verified_runtime_session_state(datetime(2026, 11, 10, 12, tzinfo=timezone.utc), ()),
            "BROKER_CALENDAR_UNVERIFIED",
        )

    def test_unverified_calendar_never_authorizes_entry(self):
        payload = json.dumps({"verified": False, "sessions": [
            {"open": "2026-11-10T09:00:00Z", "close": "2026-11-10T17:00:00Z"}
        ]})
        self.assertEqual(verified_sessions(payload), ())
        self.assertFalse(verified_entry_calendar_available(payload))

    def test_verified_session_without_news_remains_unsafe(self):
        payload = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-10T09:00:00Z", "close": "2026-11-10T17:00:00Z"}
        ]})
        self.assertTrue(verified_entry_calendar_available(payload))
        self.assertFalse(verified_news_calendar_available(None))
        self.assertEqual(
            verified_runtime_session_state(
                datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
                verified_sessions(payload),
            ),
            "OPEN",
        )

    def test_verified_empty_news_is_distinct_from_missing(self):
        self.assertTrue(verified_news_calendar_available(
            json.dumps({"verified": True, "events": []})
        ))
        self.assertFalse(verified_news_calendar_available(
            json.dumps({"verified": False, "events": []})
        ))

    def test_session_end_exclusive(self):
        payload = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-10T09:00:00Z", "close": "2026-11-10T17:00:00Z"}
        ]})
        self.assertEqual(
            verified_runtime_session_state(
                datetime(2026, 11, 10, 17, tzinfo=timezone.utc),
                verified_sessions(payload),
            ),
            "BROKER_SESSION_CLOSED",
        )


if __name__ == "__main__":
    unittest.main()
