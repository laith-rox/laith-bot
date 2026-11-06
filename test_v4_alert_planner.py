import unittest
from datetime import datetime, timedelta, timezone
from v4_alert_planner import plan_market_close_notice, plan_verified_news_notices


class AlertPlannerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 15, 30, tzinfo=timezone.utc)
        self.closes = self.now + timedelta(minutes=30)
        self.intervals = [(self.now - timedelta(hours=4), self.closes)]

    def test_market_close_warning(self):
        result = plan_market_close_notice(self.now, self.intervals, self.now)
        self.assertIn("30 دقيقة", result["message"])

    def test_duplicate_close_warning_blocked(self):
        first = plan_market_close_notice(self.now, self.intervals, self.now)
        self.assertIsNone(plan_market_close_notice(
            self.now, self.intervals, self.now, already_sent_keys={first["key"]}))

    def test_missing_broker_calendar(self):
        self.assertIsNone(plan_market_close_notice(self.now, [], self.now))

    def test_stale_quote_still_warns_about_verified_close(self):
        old = self.now - timedelta(minutes=3)
        self.assertIsNotNone(plan_market_close_notice(self.now, self.intervals, old))

    def test_not_early(self):
        earlier = self.now - timedelta(minutes=2)
        self.assertIsNone(plan_market_close_notice(earlier, self.intervals, earlier))

    def test_weekly_label(self):
        result = plan_market_close_notice(self.now, self.intervals, self.now, weekly=True)
        self.assertIn("الأسبوعي", result["message"])

    def test_news_dedupe(self):
        event = dict(id="n1", release_at=self.now + timedelta(minutes=20),
                     importance="high", calendar_verified=True)
        first = plan_verified_news_notices(self.now, [event])
        self.assertEqual(len(first), 1)
        self.assertEqual(plan_verified_news_notices(
            self.now, [event], already_sent_keys={first[0]["key"]}), [])


if __name__ == "__main__":
    unittest.main()
