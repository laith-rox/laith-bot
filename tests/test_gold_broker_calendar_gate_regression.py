"""Gold broker-calendar gate regression tests (no invented sessions or news)."""
import json
import unittest
from datetime import datetime, timezone

from v4_verified_calendar import (
    verified_entry_calendar_available,
    verified_news,
    verified_news_calendar_available,
    verified_sessions,
)
from v4_runtime import verified_runtime_session_state


def session(opened, closed):
    return json.dumps({"verified": True, "sessions": [{"open": opened, "close": closed}]})


class GoldCalendarGateTests(unittest.TestCase):
    def test_missing_calendar_blocks_gold_entry(self):
        self.assertFalse(verified_entry_calendar_available(None))
        self.assertEqual(verified_runtime_session_state(
            datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc), ()),
            "BROKER_CALENDAR_UNVERIFIED")

    def test_unverified_calendar_is_not_trusted(self):
        raw = json.dumps({"verified": False, "sessions": [
            {"open": "2026-11-09T08:00:00Z", "close": "2026-11-09T20:00:00Z"}]})
        self.assertFalse(verified_entry_calendar_available(raw))

    def test_verified_window_allows_only_its_interval(self):
        windows = verified_sessions(session("2026-11-09T08:00:00Z",
                                            "2026-11-09T20:00:00Z"))
        self.assertTrue(windows)
        self.assertEqual(verified_runtime_session_state(
            datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc), windows), "OPEN")
        self.assertEqual(verified_runtime_session_state(
            datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc), windows),
            "BROKER_SESSION_CLOSED")

    def test_saturday_overlap_is_rejected(self):
        self.assertFalse(verified_sessions(session(
            "2026-11-06T23:30:00Z", "2026-11-07T00:30:00Z")))

    def test_overlapping_sessions_are_rejected(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-09T08:00:00Z", "close": "2026-11-09T14:00:00Z"},
            {"open": "2026-11-09T13:00:00Z", "close": "2026-11-09T20:00:00Z"}]})
        self.assertFalse(verified_entry_calendar_available(raw))

    def test_naive_broker_timestamps_are_rejected(self):
        self.assertFalse(verified_sessions(session(
            "2026-11-09T08:00:00", "2026-11-09T20:00:00")))

    def test_oversized_broker_window_is_rejected(self):
        self.assertFalse(verified_sessions(session(
            "2026-11-09T08:00:00Z", "2026-11-10T09:00:00Z")))

    def test_missing_news_is_not_misrepresented_as_verified(self):
        self.assertEqual(verified_news(None), ())
        self.assertEqual(verified_news('{"verified":false,"events":[]}'), ())

    def test_verified_empty_news_calendar_is_valid(self):
        self.assertTrue(verified_news_calendar_available('{"verified":true,"events":[]}'))

    def test_missing_or_unverified_news_calendar_is_blocked(self):
        self.assertFalse(verified_news_calendar_available(None))
        self.assertFalse(verified_news_calendar_available('{"verified":false,"events":[]}'))
        self.assertFalse(verified_news_calendar_available('not-json'))

    def test_malformed_verified_news_event_is_blocked(self):
        raw = json.dumps({"verified": True, "events": [{"title": "Sample"}]})
        self.assertFalse(verified_news_calendar_available(raw))

    def test_unpublished_actual_news_is_rejected(self):
        raw = json.dumps({"verified": True, "events": [{
            "id": "sample", "title": "Sample release",
            "release_at": "2026-11-09T13:00:00Z", "actual": 1.5}]})
        self.assertEqual(verified_news(raw), ())


if __name__ == "__main__":
    unittest.main()
