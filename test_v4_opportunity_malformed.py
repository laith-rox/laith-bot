import unittest
from v4_opportunity_gate import evaluate_opportunity


class MalformedOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.q = dict(quick5m=dict(side="BUY", entry_allowed=True, buy=7,
                                  higher_side="BUY", atr5=5.0,
                                  current_price=3000.0, current_open=2999.5))
        self.ref = dict(timing_aligned=True, delayed_reference=False,
                        current_five_minute_candle=True)

    def test_valid_quote(self):
        self.assertEqual(evaluate_opportunity(self.q, self.ref)[0], True)

    def test_nan_price_blocked(self):
        self.q["quick5m"]["current_price"] = float("nan")
        self.assertEqual(evaluate_opportunity(self.q, self.ref)[0], False)

    def test_infinite_atr_blocked(self):
        self.q["quick5m"]["atr5"] = float("inf")
        self.assertEqual(evaluate_opportunity(self.q, self.ref)[0], False)

    def test_malformed_score_blocked(self):
        self.q["quick5m"]["buy"] = "unknown"
        self.assertEqual(evaluate_opportunity(self.q, self.ref)[0], False)

    def test_missing_open_blocked(self):
        self.q["quick5m"]["current_open"] = None
        self.assertEqual(evaluate_opportunity(self.q, self.ref)[0], False)

if __name__ == "__main__":
    unittest.main()
