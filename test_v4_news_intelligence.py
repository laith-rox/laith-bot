import unittest
from datetime import datetime, timedelta, timezone
from v4_news_intelligence import plan_pre_news_alert

class NewsPlannerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)
        self.event = dict(id="cpi-us", release_at=self.now + timedelta(minutes=20),
                          title="US CPI", importance="high", calendar_verified=True,
                          consensus="2.8%", previous="2.9%", risk="مرتفعة")

    def test_alert_at_20_minutes(self):
        self.assertIn("20 دقيقة", plan_pre_news_alert(self.now, self.event)["message"])

    def test_no_early_alert(self):
        self.assertIsNone(plan_pre_news_alert(self.now - timedelta(minutes=1), self.event))

    def test_no_late_alert(self):
        self.assertIsNone(plan_pre_news_alert(self.now + timedelta(minutes=1), self.event))

    def test_unverified_calendar_blocks(self):
        self.event["calendar_verified"] = False
        self.assertIsNone(plan_pre_news_alert(self.now, self.event))

    def test_low_impact_blocks(self):
        self.event["importance"] = "low"
        self.assertIsNone(plan_pre_news_alert(self.now, self.event))

    def test_missing_consensus_not_fabricated(self):
        self.event["consensus"] = None
        self.assertIn("غير متاح", plan_pre_news_alert(self.now, self.event)["message"])

    def test_key_deterministic(self):
        a = plan_pre_news_alert(self.now, self.event)
        b = plan_pre_news_alert(self.now, self.event)
        self.assertEqual(a["key"], b["key"])

if __name__ == "__main__":
    unittest.main()
