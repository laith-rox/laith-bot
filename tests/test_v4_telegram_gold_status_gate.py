"""Regression: Telegram /status must explain gold's fail-closed broker/news gate."""
import unittest
from v4_telegram import status_message


class Store:
    def __init__(self, market_state):
        self.market_state = market_state

    def get(self, key, default=None):
        if key == "v4_market_status":
            return self.market_state
        return default


class GoldStatusGateTests(unittest.TestCase):
    def test_unverified_broker_calendar_explained(self):
        text = status_message(Store("BROKER_CALENDAR_UNVERIFIED"))
        self.assertIn("جلسات وسيط الذهب غير موثقة", text)
        self.assertIn("لا توجد إشارة دخول ذهب", text)

    def test_unverified_news_calendar_explained(self):
        text = status_message(Store("NEWS_CALENDAR_UNVERIFIED"))
        self.assertIn("تقويم الأخبار غير موثق", text)
        self.assertIn("لا توجد إشارة دخول ذهب", text)

    def test_open_session_does_not_claim_trade(self):
        text = status_message(Store("OPEN"))
        self.assertIn("حالة سوق الذهب: <b>OPEN</b>", text)
        self.assertNotIn("لا توجد إشارة دخول ذهب:", text)

    def test_untrusted_state_not_echoed_into_html(self):
        text = status_message(Store("<script>unsafe</script>"))
        self.assertNotIn("<script>", text)
        self.assertIn("UNKNOWN", text)


if __name__ == "__main__":
    unittest.main()
