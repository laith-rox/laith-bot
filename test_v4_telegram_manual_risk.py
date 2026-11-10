import unittest
from v4_telegram import manual_risk_line, quick_message


class TelegramManualRiskTests(unittest.TestCase):
    def setUp(self):
        self.trade = {"side": "BUY", "entry": 4000, "stop": 3995,
                      "target": 4010, "rr": 2, "current_five_minute_candle": True}
        self.specs = {"contract_oz_per_lot": 100, "usd_per_quote_unit": 1,
                      "lot_step": .01, "min_lot": .01, "max_lot": 10}

    def test_unverified_specs_do_not_show_lot(self):
        self.assertIn("غير محسوب", manual_risk_line(self.trade))
        self.assertNotIn("سقف اللوت اليدوي", quick_message(self.trade))

    def test_verified_specs_show_manual_ceiling(self):
        self.trade.update(verified_broker_specs=self.specs, risk_budget_usd=5)
        msg = quick_message(self.trade)
        self.assertIn("سقف اللوت اليدوي: 0.0100", msg)
        self.assertIn("ليست أمر تنفيذ", msg)

    def test_too_small_budget_fails_closed(self):
        self.assertIn("انتظار", manual_risk_line(self.trade, self.specs, 1))

    def test_invalid_stop_fails_closed(self):
        self.trade["stop"] = 4005
        self.assertIn("انتظار", manual_risk_line(self.trade, self.specs, 5))


if __name__ == "__main__":
    unittest.main()
