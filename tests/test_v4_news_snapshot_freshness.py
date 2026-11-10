"""Gold verified-news snapshot freshness: never allow stale or future claims."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from v4_verified_calendar import verified_news_calendar_available


class VerifiedNewsFreshnessTests(unittest.TestCase):
    def test_expired_snapshot_fails_closed(self):
        now = datetime.now(timezone.utc)
        payload = {"verified": True, "events": [], "verified_at": (now - timedelta(hours=3)).isoformat(),
                   "expires_at": (now - timedelta(hours=1)).isoformat()}
        self.assertFalse(verified_news_calendar_available(json.dumps(payload)))

    def test_future_verified_timestamp_fails_closed(self):
        now = datetime.now(timezone.utc)
        payload = {"verified": True, "events": [], "verified_at": (now + timedelta(hours=1)).isoformat(),
                   "expires_at": (now + timedelta(hours=2)).isoformat()}
        self.assertFalse(verified_news_calendar_available(json.dumps(payload)))

    def test_current_snapshot_remains_valid(self):
        now = datetime.now(timezone.utc)
        payload = {"verified": True, "events": [], "verified_at": (now - timedelta(minutes=2)).isoformat(),
                   "expires_at": (now + timedelta(minutes=30)).isoformat()}
        self.assertTrue(verified_news_calendar_available(json.dumps(payload)))

    def test_malformed_expiry_fails_closed(self):
        payload = {"verified": True, "events": [], "expires_at": "not-a-date"}
        self.assertFalse(verified_news_calendar_available(json.dumps(payload)))


if __name__ == "__main__":
    unittest.main()
