import unittest
from v4_opportunity_diagnostic import diagnose_wait


class OpportunityDiagnosticTests(unittest.TestCase):
    def test_missing_checks_are_unknown_not_zero(self):
        result = diagnose_wait({"side": "WAIT", "reason": "v4_no_trade_zone"})
        self.assertIsNone(result["buy_score"])
        self.assertTrue(result["buy_checks_missing"])
        self.assertFalse(result["eligible_for_review"])

    def test_five_of_seven_wait_is_review_only(self):
        decision = {"side": "WAIT", "reason": "v4_no_trade_zone", "checks": {
            "BUY": [True] * 5 + [False] * 2, "SELL": [False] * 7}}
        result = diagnose_wait(decision)
        self.assertEqual(result["buy_score"], 5)
        self.assertTrue(result["eligible_for_review"])
        self.assertEqual(decision["side"], "WAIT")

    def test_below_threshold_does_not_flag(self):
        result = diagnose_wait({"side": "WAIT", "checks": {
            "BUY": [True] * 4 + [False] * 3, "SELL": [False] * 7}})
        self.assertFalse(result["eligible_for_review"])

    def test_zone_and_gate_reasons_preserved(self):
        result = diagnose_wait({"side": "WAIT", "v4": {
            "no_trade_zone": {"reasons": ["failed_breakout"]},
            "intelligence": {"entry_gate": {"reasons": ["stale_market_data"]}}}})
        self.assertEqual(result["zone_reasons"], ["failed_breakout"])
        self.assertEqual(result["entry_gate_reasons"], ["stale_market_data"])


if __name__ == "__main__":
    unittest.main()
