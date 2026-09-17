import unittest

from v4_telegram import quick_message


class V4TelegramDisplayTests(unittest.TestCase):
    def test_quick_message_shows_calibrated_strength_and_history(self):
        trade = {
            "side": "SELL",
            "score": 6,
            "condition_percent": 86,
            "strength": "متوسطة",
            "raw_strength": "قوية",
            "strength_adjustments": ["المخاطرة مرتفعة", "النظام الرسمي WAIT"],
            "historical_sample": 20,
            "historical_positive": 7,
            "historical_positive_rate": 35,
            "risk_level": "مرتفعة",
            "risk_reasons": ["تذبذب مرتفع"],
            "rsi": 48.0,
            "conditions": [],
            "entry": 4300.0,
            "stop": 4305.0,
            "target": 4292.5,
            "rr": 1.5,
            "session": "ASIA",
            "volatility_regime": "HIGH",
        }
        message = quick_message(trade)
        self.assertIn("6/7 = 86%", message)
        self.assertIn("القوة الخام: قوية", message)
        self.assertIn("المعروضة: <b>متوسطة</b>", message)
        self.assertIn("7/20 موجبة (35%)", message)
        self.assertIn("ليس احتمال نجاح", message)

    def test_quick_message_handles_no_history(self):
        trade = {
            "side": "BUY",
            "score": 5,
            "condition_percent": 71,
            "strength": "متوسطة",
            "risk_level": "متوسطة",
            "risk_reasons": [],
            "rsi": 55.0,
            "conditions": [],
            "entry": 4300.0,
            "stop": 4297.0,
            "target": 4304.5,
            "rr": 1.5,
            "session": "ASIA",
            "volatility_regime": "NORMAL",
        }
        message = quick_message(trade)
        self.assertIn("لا توجد عينة مقاسة كافية بعد", message)


if __name__ == "__main__":
    unittest.main()
