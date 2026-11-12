import unittest

from v4_telegram import quick_message, continuation_message, paper_open_message, paper_close_message


class V4TelegramDisplayTests(unittest.TestCase):
    def test_quick_message_is_compact_and_keeps_essentials(self):
        trade = {
            "side": "SELL", "score": 6, "strength": "متوسطة",
            "risk_level": "مرتفعة", "risk_reasons": ["تذبذب مرتفع"],
            "entry": 4300.0, "stop": 4305.0, "target": 4292.5, "rr": 1.5,
        }
        message = quick_message(trade)
        self.assertIn("بوت ليث | الذهب", message)
        self.assertIn("بيع", message)
        self.assertIn("6/7", message)
        self.assertIn("4300.00", message)
        self.assertIn("4305.00", message)
        self.assertIn("💰 الدخول:", message)
        self.assertIn("🛑 الوقف:", message)
        self.assertIn("🎯 الهدف:", message)
        self.assertIn("4292.50", message)
        self.assertIn("المخاطرة", message)
        self.assertNotIn("النتائج المرصودة", message)
        self.assertNotIn("RSI", message)
        self.assertLess(len(message.splitlines()), 20)


    def test_royal_style_covers_paper_open_continuation_and_close(self):
        trade = {
            "side": "SELL", "entry": 3960.58, "stop": 3970.41,
            "tp1": 3947.93, "tp2": 3942.31, "signal_score": 5,
            "signal_strength": "متوسطة", "research_v4": {"session": "LONDON"},
        }
        snapshot = {
            "side": "SELL", "entry": 3960.58, "stop": 3970.41,
            "tp1": 3947.93, "tp2": 3942.31, "price": 3950.0,
            "score": 5, "state": "متوسطة", "adverse_correction": True,
        }
        closed = {"side": "SELL", "outcome": "TP2", "r": 1.857}
        for message in (
            paper_open_message(trade),
            continuation_message(snapshot),
            paper_close_message(closed, {"net_r": 1.429}),
        ):
            self.assertIn("بوت ليث | الذهب", message)
            self.assertIn("━━━━━━", message)
            self.assertIn("ورقي", message)
        self.assertIn("3960.58", paper_open_message(trade))
        self.assertIn("3970.41", continuation_message(snapshot))
        self.assertIn("🎯 الهدف الأول:", continuation_message(snapshot))
        self.assertIn("🎯 الهدف الثاني:", paper_open_message(trade))
        self.assertIn("💰 الدخول:", paper_open_message(trade))
        self.assertIn("🛑 الوقف:", paper_open_message(trade))
        self.assertNotIn("BLACK DIAMOND ROYAL", paper_open_message(trade))
        self.assertIn("تصحيح قوي عكس الصفقة", continuation_message(snapshot))
        self.assertIn("1.857", paper_close_message(closed, {"net_r": 1.429}))

if __name__ == "__main__":
    unittest.main()
