import unittest

from v4_quick_balance import attach_condition_balance, condition_balance_line, quick_message


class V4QuickBalanceTests(unittest.TestCase):
    def test_sell_shows_buy_conditions_in_parentheses(self):
        setup = {"side": "SELL"}
        decision = {"buy": 2, "sell": 6}
        trade = attach_condition_balance(setup, decision)
        self.assertEqual(trade["sell_score"], 6)
        self.assertEqual(trade["buy_score"], 2)
        self.assertEqual(
            condition_balance_line(trade),
            "📊 شروط البيع: <b>6/7 = 86%</b> (شروط الشراء: 2/7 = 29%)",
        )

    def test_buy_shows_sell_conditions_in_parentheses(self):
        setup = {"side": "BUY"}
        decision = {"buy": 5, "sell": 3}
        trade = attach_condition_balance(setup, decision)
        self.assertEqual(
            condition_balance_line(trade),
            "📊 شروط الشراء: <b>5/7 = 71%</b> (شروط البيع: 3/7 = 43%)",
        )

    def test_message_replaces_only_condition_summary(self):
        trade = {
            "side": "SELL",
            "score": 6,
            "condition_percent": 86,
            "strength": "متوسطة",
            "raw_strength": "قوية",
            "strength_adjustments": ["المخاطرة مرتفعة"],
            "risk_level": "مرتفعة",
            "risk_reasons": [],
            "historical_sample": 0,
            "rsi": 48.0,
            "conditions": [],
            "entry": 4300.0,
            "stop": 4305.0,
            "target": 4292.5,
            "rr": 1.5,
            "session": "ASIA",
            "volatility_regime": "HIGH",
            "buy_score": 2,
            "sell_score": 6,
            "buy_percent": 29,
            "sell_percent": 86,
        }
        message = quick_message(trade)
        self.assertIn("شروط البيع: <b>6/7 = 86%</b> (شروط الشراء: 2/7 = 29%)", message)
        self.assertNotIn("📊 تحقق الشروط:", message)


if __name__ == "__main__":
    unittest.main()
