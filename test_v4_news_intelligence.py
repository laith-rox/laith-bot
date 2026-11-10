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


class NewsTelegramMarkupSafetyTests(unittest.TestCase):
    def test_external_calendar_fields_are_html_escaped(self):
        from datetime import datetime, timedelta, timezone
        from v4_news_intelligence import plan_pre_news_alert
        now = datetime(2026, 11, 9, 13, 0, tzinfo=timezone.utc)
        event = {"id": "news-safe", "release_at": now + timedelta(minutes=20),
                 "importance": "high", "calendar_verified": True,
                 "title": "<b>FAKE</b>", "consensus": "1<&2",
                 "previous": "<i>oops</i>", "conditional_scenario": "<script>x</script>",
                 "risk": "high & rising"}
        notice = plan_pre_news_alert(now, event)
        self.assertIsNotNone(notice)
        message = notice["message"]
        for unsafe in ("<b>FAKE</b>", "<i>oops</i>", "<script>x</script>"):
            self.assertNotIn(unsafe, message)
        self.assertIn("&lt;b&gt;FAKE&lt;/b&gt;", message)
        self.assertIn("1&lt;&amp;2", message)
        self.assertIn("high &amp; rising", message)
