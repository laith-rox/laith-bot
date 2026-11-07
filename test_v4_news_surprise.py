import unittest
import json
from datetime import datetime, timedelta, timezone
from v4_news_surprise import plan_post_news_alert
from v4_alert_planner import plan_verified_news_notices
from v4_verified_calendar import verified_news

UTC = timezone.utc

class PostReleaseTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 11, 6, 13, 30, tzinfo=UTC)
        self.event = dict(id="us-cpi", title="US CPI", release_at=self.at,
            importance="high", calendar_verified=True, actual_verified=True,
            actual_source="Official statistics agency", actual_published_at=self.at + timedelta(seconds=15),
            actual="3.1%", consensus="2.8%")

    def test_verified_surprise_and_dedupe(self):
        now = self.at + timedelta(minutes=1)
        notice = plan_post_news_alert(now, self.event)
        self.assertIn("+0.3", notice["message"])
        self.assertIn("لا نستنتج اتجاه الذهب", notice["message"])
        self.assertEqual(len(plan_verified_news_notices(now, [self.event])), 1)
        self.assertEqual(plan_verified_news_notices(now, [self.event], already_sent_keys=[notice["key"]]), [])

    def test_no_lookahead_or_unverified_release(self):
        self.assertIsNone(plan_post_news_alert(self.at, self.event))
        for field in ("calendar_verified", "actual_verified"):
            bad = dict(self.event, **{field: False})
            self.assertIsNone(plan_post_news_alert(self.at + timedelta(minutes=1), bad))
        bad = dict(self.event, actual_published_at=self.at - timedelta(seconds=1))
        self.assertIsNone(plan_post_news_alert(self.at + timedelta(minutes=1), bad))

    def test_stale_missing_and_malformed(self):
        for change in ({"actual": None}, {"actual": "NaN"}, {"consensus": "?"},
                       {"actual_source": ""}, {"actual_published_at": None}):
            self.assertIsNone(plan_post_news_alert(self.at + timedelta(minutes=1), dict(self.event, **change)))
        self.assertIsNone(plan_post_news_alert(self.at + timedelta(hours=1), self.event))

    def test_verified_adapter_parses_published_time(self):
        event = dict(self.event, release_at=self.at.isoformat(),
                     actual_published_at=self.event["actual_published_at"].isoformat())
        result = verified_news(json.dumps({"verified": True, "events": [event]}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["actual_published_at"], self.event["actual_published_at"])

if __name__ == "__main__":
    unittest.main()
