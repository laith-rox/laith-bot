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

    def test_truthy_check_values_match_v4_scoring(self):
        result = diagnose_wait({"side": "WAIT", "checks": {
            "BUY": [1, 1, 1, 1, 1, 0, 0], "SELL": [0] * 7}})
        self.assertEqual(result["buy_score"], 5)
        self.assertTrue(result["eligible_for_review"])

    def test_tied_strong_directions_are_not_false_missed_opportunity(self):
        result = diagnose_wait({"side": "WAIT", "checks": {
            "BUY": [True] * 5 + [False] * 2,
            "SELL": [True] * 5 + [False] * 2}})
        self.assertIsNone(result["dominant_side"])
        self.assertFalse(result["eligible_for_review"])

    def test_missing_opposite_checks_are_not_assumed_weak(self):
        result = diagnose_wait({"side": "WAIT", "checks": {
            "BUY": [True] * 6 + [False]}})
        self.assertIsNone(result["dominant_side"])
        self.assertFalse(result["eligible_for_review"])

    def test_below_threshold_does_not_flag(self):
        result = diagnose_wait({"side": "WAIT", "checks": {
            "BUY": [True] * 4 + [False] * 3, "SELL": [False] * 7}})
        self.assertFalse(result["eligible_for_review"])

    def test_analysis_attaches_diagnostic_without_changing_side(self):
        from unittest.mock import patch
        from v4_research import analyze_v4
        base = {"side": "WAIT", "reason": "v3_no_trade_zone", "checks": {
            "BUY": [True] * 5 + [False] * 2,
            "SELL": [False] * 7}}
        base["price"], base["atr"] = 100.0, 1.0
        with patch("v4_research.analyze_v3", return_value=base.copy()), \
             patch("v4_research.enrich_decision", side_effect=lambda d, bars, now: d), \
             patch("v4_research.market_brain", return_value={}), \
             patch("v4_research.market_adaptation", return_value={}):
            # Baseline exposes a directional candidate; diagnostics must not change it.
            result = analyze_v4([], None)
        self.assertEqual(result["side"], "BUY")
        self.assertIn("opportunity_diagnostic", result["v4"])
        self.assertEqual(result["v4"]["opportunity_diagnostic"]["buy_score"], 5)

    def test_zone_and_gate_reasons_preserved(self):
        result = diagnose_wait({"side": "WAIT", "v4": {
            "no_trade_zone": {"reasons": ["failed_breakout"]},
            "intelligence": {"entry_gate": {"reasons": ["stale_market_data"]}}}})
        self.assertEqual(result["zone_reasons"], ["failed_breakout"])
        self.assertEqual(result["entry_gate_reasons"], ["stale_market_data"])


if __name__ == "__main__":
    unittest.main()
