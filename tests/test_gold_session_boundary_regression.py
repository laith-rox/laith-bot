"""Regression checks for gold session boundaries and calendar fail-closed behavior."""
import json
import unittest
from datetime import datetime, timezone

from v4_verified_calendar import verified_sessions, verified_news
from v4_runtime import verified_runtime_session_state


def utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def schedule(*windows):
    return json.dumps({"verified": True, "sessions": [
        {"open": start, "close": end} for start, end in windows
    ]})


class GoldSessionBoundaryRegression(unittest.TestCase):
    def test_open_is_inclusive_close_is_exclusive(self):
        sessions = verified_sessions(schedule(
            ("2026-11-09T08:00:00Z", "2026-11-09T20:00:00Z")))
        self.assertEqual(verified_runtime_session_state(
            utc("2026-11-09T08:00:00Z"), sessions), "OPEN")
        self.assertEqual(verified_runtime_session_state(
            utc("2026-11-09T20:00:00Z"), sessions), "BROKER_SESSION_CLOSED")

    def test_adjacent_verified_sessions_are_valid(self):
        sessions = verified_sessions(schedule(
            ("2026-11-09T08:00:00Z", "2026-11-09T12:00:00Z"),
            ("2026-11-09T12:00:00Z", "2026-11-09T20:00:00Z")))
        self.assertEqual(len(sessions), 2)

    def test_overlapping_sessions_fail_closed(self):
        self.assertEqual(verified_sessions(schedule(
            ("2026-11-09T08:00:00Z", "2026-11-09T12:01:00Z"),
            ("2026-11-09T12:00:00Z", "2026-11-09T20:00:00Z"))), ())

    def test_weekend_crossing_fails_closed_even_with_timezone_offset(self):
        self.assertEqual(verified_sessions(schedule(
            ("2026-11-07T00:30:00+02:00", "2026-11-07T04:00:00+02:00"))), ())

    def test_actual_news_before_release_is_rejected(self):
        raw = json.dumps({"verified": True, "events": [{
            "id": "release-1", "title": "Example",
            "release_at": "2026-11-09T13:00:00Z",
            "actual": 2.0,
            "actual_published_at": "2026-11-09T12:59:00Z"}]})
        self.assertEqual(verified_news(raw), ())


if __name__ == "__main__":
    unittest.main()
