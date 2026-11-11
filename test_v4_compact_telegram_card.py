import unittest
from v4_quick_balance import quick_message


class CompactTelegramCardTests(unittest.TestCase):
    def test_internal_diagnostics_not_displayed(self):
        trade = {
            "side": "SELL", "strength": "متوسطة", "score": 7,
            "entry": 3986.79, "stop": 3988.79, "target": 3983.79,
            "rr": 1.5, "risk_level": "مرتفعة", "cautious_entry": True,
            "buy_score": 0, "sell_score": 7,
            "dual_brain": {"market": {"market_scenarios": {"preferred": "SELL"}},
                           "execution": {"action": "CAUTIOUS"}},
            "adaptive": {"feature_17_validity": {"status": "VALID"},
                         "feature_20_execution_cost": {"status": "SPREAD_UNKNOWN"}},
            "adaptive_market": {"feature_13_session": {"name": "NEW_YORK"}},
            "delayed_reference": True,
        }
        message = quick_message(trade)
        for visible in ("SELL", "3986.79", "3988.79", "3983.79", "إغلاق شمعة 5د"):
            self.assertIn(visible, message)
        self.assertTrue(message.splitlines()[-1].startswith("🟡 الحالة:"))
        for hidden in ("العقلين:", "جلسة NEW_YORK", "SPREAD_UNKNOWN", "صلاحية VALID", "أسلوب TREND", "تحديث الفرصة:", "📡 المرجع:", "⑦ التصحيح:"):
            self.assertNotIn(hidden, message)


if __name__ == "__main__":
    unittest.main()
