"""Gold calendar trust boundary: malformed metadata must fail closed.

These tests use a synthetic feed only; they do not claim live news verification.
"""
import io
import json
import unittest
from datetime import datetime, timedelta, timezone

from v4_free_news_calendar import fetch_verified_news


class CalendarMetadataRegression(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 12, 1, 0, tzinfo=timezone.utc)
        self.event = {
            "id": "synthetic-usd-1", "title": "Synthetic USD release",
            "currency": "USD", "impact": "high",
            "time": (self.now + timedelta(hours=1)).isoformat(),
            "status": "scheduled", "confidence": "official",
        }
        self.payload = {
            "server_time": self.now.timestamp(),
            "generated_at": self.now.isoformat(),
            "count": 1, "events": [self.event],
        }

    def fetch(self):
        data = json.dumps(self.payload).encode("utf-8")
        return fetch_verified_news(
            now=self.now,
            opener=lambda request, timeout: io.BytesIO(data),
        )

    def test_valid_synthetic_snapshot(self):
        self.assertTrue(json.loads(self.fetch())["verified"])

    def test_boolean_server_clock_is_not_a_timestamp(self):
        self.payload["server_time"] = True
        with self.assertRaisesRegex(ValueError, "stale_calendar_clock"):
            self.fetch()

    def test_nonfinite_server_clocks_fail_closed(self):
        for clock in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(clock=repr(clock)):
                self.payload["server_time"] = clock
                with self.assertRaisesRegex(ValueError, "stale_calendar_clock"):
                    self.fetch()

    def test_snapshot_from_future_fails_closed(self):
        self.payload["generated_at"] = (self.now + timedelta(minutes=3)).isoformat()
        with self.assertRaisesRegex(ValueError, "stale_calendar_snapshot"):
            self.fetch()

    def test_duplicate_release_identity_fails_closed(self):
        self.payload["events"].append(dict(self.event, id="synthetic-usd-2"))
        self.payload["count"] = 2
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_calendar_event"):
            self.fetch()

    def test_release_outside_feed_window_fails_closed(self):
        self.event["time"] = (self.now + timedelta(days=6)).isoformat()
        with self.assertRaisesRegex(ValueError, "release_outside_calendar_window"):
            self.fetch()

    def test_oversized_event_feed_fails_closed(self):
        self.payload["events"] = [dict(self.event, id=f"synthetic-{i}") for i in range(1001)]
        self.payload["count"] = 1001
        with self.assertRaisesRegex(ValueError, "calendar_too_many_events"):
            self.fetch()


if __name__ == "__main__":
    unittest.main()
