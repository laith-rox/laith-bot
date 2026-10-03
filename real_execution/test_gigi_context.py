import unittest

import gigi_context


class GigiContextTests(unittest.TestCase):
    def test_aligned_buy_gets_support(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"TREND_UP","h4_bias":"UP","effort_result":"EXPANSION_CONFIRMED"},
            {"bias":"BULLISH_GOLD"},
            {"regime":"CLEAR"},
        )
        self.assertEqual(out["alignment"],"STRONG_SUPPORT")
        self.assertGreaterEqual(out["score"],3)

    def test_conflicting_buy_is_flagged(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"TREND_DOWN","h4_bias":"DOWN","effort_result":"BALANCED"},
            {"bias":"BEARISH_GOLD"},
            {"regime":"CLEAR"},
        )
        self.assertIn(out["alignment"],("CONFLICT","STRONG_CONFLICT"))
        self.assertLess(out["score"],0)

    def test_high_impact_event_marks_event_driven(self):
        out=gigi_context.evaluate(
            "SELL",
            {"name":"TREND_DOWN","h4_bias":"DOWN","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"HIGH_IMPACT_WINDOW"},
        )
        self.assertEqual(out["market_state"],"EVENT_DRIVEN")
        self.assertIn("high_impact_usd_window",out["reasons"])

    def test_score_is_not_probability(self):
        out=gigi_context.evaluate("WAIT",{}, {}, {"regime":"UNKNOWN"})
        self.assertEqual(out["note"],"alignment_score_not_probability")

    def test_liquidity_sweep_can_support_buy(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"SELL_SIDE_SWEEP","pressure":"BULLISH"},
        )
        self.assertGreater(out["score"],0)
        self.assertIn("liquidity_supports_buy",out["reasons"])



if __name__=="__main__":
    unittest.main()
