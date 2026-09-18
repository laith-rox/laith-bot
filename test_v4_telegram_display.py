import unittest

from v4_telegram import quick_message


class V4TelegramDisplayTests(unittest.TestCase):
    def test_quick_message_is_compact_and_keeps_essentials(self):
        trade = {
            "side": "SELL", "score": 6, "strength": "متوسطة",
            "risk_level": "مرتفعة", "risk_reasons": ["تذبذب مرتفع"],
            "entry": 4300.0, "stop": 4305.0, "target": 4292.5, "rr": 1.5,
        }
        message = quick_message(trade)
        self.assertIn("V4 سريع — 5د", message)
        self.assertIn("SELL", message)
        self.assertIn("6/7", message)
        self.assertIn("4300.00", message)
        self.assertIn("4305.00", message)
        self.assertIn("4292.50", message)
        self.assertIn("المخاطرة", message)
        self.assertNotIn("النتائج المرصودة", message)
        self.assertNotIn("RSI", message)
        self.assertLess(len(message.splitlines()), 10)


if __name__ == "__main__":
    unittest.main()
