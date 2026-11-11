"""Regression checks: unverified economic events must never authorize gold entries."""
import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from v4_free_news_calendar import fetch_verified_news


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class CalendarTrustBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
        self.payload = {
            "server_time": self.now.timestamp(),
            "generated_at": self.now.isoformat(),
            "count": 1,
            "events": [{
                "id": "usd-release-1",
                "title": "USD release",
                "currency": "USD",
                "impact": "high",
                "time": "2026-11-11T21:00:00Z",
                "status": "scheduled",
                "confidence": "official",
            }],
        }

    def fetch(self):
        data = json.dumps(self.payload).encode("utf-8")
        return fetch_verified_news(
            now=self.now,
            opener=lambda request, timeout: _Response(data),
        )

    def test_documented_verified_event_passes(self):
        result = json.loads(self.fetch())
        self.assertTrue(result["verified"])
        self.assertEqual(len(result["events"]), 1)

    def test_missing_confidence_fails_closed(self):
        del self.payload["events"][0]["confidence"]
        with self.assertRaisesRegex(ValueError, "uncertain_calendar_event"):
            self.fetch()

    def test_unknown_status_fails_closed(self):
        self.payload["events"][0]["status"] = "tentative"
        with self.assertRaisesRegex(ValueError, "uncertain_calendar_event"):
            self.fetch()

    def test_untrusted_confidence_fails_closed(self):
        self.payload["events"][0]["confidence"] = "estimated"
        with self.assertRaisesRegex(ValueError, "uncertain_calendar_event"):
            self.fetch()


if __name__ == "__main__":
    unittest.main()
