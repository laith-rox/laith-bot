import unittest
from v4_opportunity_gate import evaluate_opportunity


class OpportunityGateTests(unittest.TestCase):
    def setUp(self):
        self.decision = {"quick5m": {"entry_allowed": True, "side": "BUY", "buy": 7,
                          "higher_side": "BUY", "atr5": 4, "current_price": 100.5,
                          "current_open": 100}}
        self.reference = {"timing_aligned": True, "delayed_reference": False,
                          "current_five_minute_candle": True}

    def test_confirmed_opportunity(self):
        self.assertEqual(evaluate_opportunity(self.decision, self.reference),
                         (True, "confirmed_opportunity"))

    def test_weak_signal_waits(self):
        self.decision["quick5m"]["buy"] = 5
        self.assertFalse(evaluate_opportunity(self.decision, self.reference)[0])

    def test_higher_timeframe_conflict_waits(self):
        self.decision["quick5m"]["higher_side"] = "SELL"
        self.assertFalse(evaluate_opportunity(self.decision, self.reference)[0])

    def test_delayed_reference_waits(self):
        self.reference["delayed_reference"] = True
        self.assertFalse(evaluate_opportunity(self.decision, self.reference)[0])

    def test_late_entry_waits(self):
        self.decision["quick5m"]["current_price"] = 102
        self.assertFalse(evaluate_opportunity(self.decision, self.reference)[0])

    def test_news_risk_waits(self):
        self.assertFalse(evaluate_opportunity(self.decision, self.reference, news_clear=False)[0])


if __name__ == "__main__":
    unittest.main()
