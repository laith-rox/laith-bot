import unittest

from v4_quick_balance import (
    attach_condition_balance,
    condition_balance_line,
    correction_block,
    quick_message,
)


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

    def test_attachs_existing_correction_map_without_changing_side(self):
        setup = {"side": "BUY"}
        decision = {
            "buy": 6,
            "sell": 2,
            "v4": {
                "correction": {
                    "direction": "DOWN",
                    "strength": "MEDIUM",
                    "triggered": True,
                    "target1": 4288.4,
                    "target2": 4281.2,
                    "invalidation": 4307.0,
                    "start_zone": {"low": 4300.0, "center": 4301.0, "high": 4302.0},
                }
            },
        }
        trade = attach_condition_balance(setup, decision)
        self.assertEqual(trade["side"], "BUY")
        self.assertEqual(trade["correction_direction"], "DOWN")
        self.assertEqual(trade["correction_target1"], 4288.4)
        self.assertEqual(trade["correction_target2"], 4281.2)
        self.assertTrue(trade["correction_triggered"])

    def test_correction_block_formats_down_and_up_targets(self):
        buy_trade = {
            "correction_direction": "DOWN",
            "correction_strength": "MEDIUM",
            "correction_triggered": True,
            "correction_target1": 4288.4,
            "correction_target2": 4281.2,
            "correction_invalidation": 4307.0,
        }
        lines = correction_block(buy_trade)
        self.assertIn("توقع التصحيح: <b>نزول</b>", lines[0])
        self.assertIn("الأقرب 4288.40 | الأعمق 4281.20", lines[1])
        self.assertIn("4307.00", lines[2])

        sell_trade = {
            "correction_direction": "UP",
            "correction_strength": "STRONG",
            "correction_triggered": False,
            "correction_target1": 4310.0,
            "correction_target2": 4318.5,
        }
        lines2 = correction_block(sell_trade)
        self.assertIn("توقع التصحيح: <b>صعود</b>", lines2[0])
        self.assertIn("القوة: قوية", lines2[0])
        self.assertIn("الحالة: مراقبة", lines2[0])

    def test_message_replaces_condition_summary_and_adds_correction_targets(self):
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
            "correction_direction": "UP",
            "correction_strength": "MEDIUM",
            "correction_triggered": True,
            "correction_target1": 4304.0,
            "correction_target2": 4308.0,
            "correction_invalidation": 4294.0,
        }
        message = quick_message(trade)
        self.assertIn("شروط البيع: <b>6/7 = 86%</b> (شروط الشراء: 2/7 = 29%)", message)
        self.assertNotIn("📊 تحقق الشروط:", message)
        self.assertIn("توقع التصحيح: <b>صعود</b>", message)
        self.assertIn("الأقرب 4304.00 | الأعمق 4308.00", message)
        self.assertIn("إبطال توقع التصحيح: 4294.00", message)


if __name__ == "__main__":
    unittest.main()
