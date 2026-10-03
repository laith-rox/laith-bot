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


    def test_first_post_event_spike_is_flagged_as_untrusted(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"TREND_UP","h4_bias":"UP","effort_result":"BALANCED"},
            {"bias":"BULLISH_GOLD"},
            {"regime":"HIGH_IMPACT_WINDOW","phase":"HIGH_EVENT_SHOCK_0_5M"},
            {"event":"NONE","pressure":"NEUTRAL"},
        )
        self.assertEqual(out["market_state"],"EVENT_DRIVEN")
        self.assertIn("first_spike_untrusted",out["reasons"])


    def test_positioning_deleveraging_supports_sell_caution(self):
        out=gigi_context.evaluate(
            "SELL",
            {"name":"TREND_DOWN","h4_bias":"DOWN","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"LONG_BIASED_DELEVERAGING","crowding":"NORMAL"},
        )
        self.assertIn("positioning_supports_sell",out["reasons"])


    def test_options_priced_move_is_context_not_direction(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"PRICED_MOVE_COMPRESSION"},
        )
        self.assertEqual(out["volatility_state"],"PRICED_MOVE_COMPRESSION")
        self.assertIn("options_price_move_before_realized_expansion",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_broad_etf_inflow_supports_buy(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"BROAD_INFLOW"},
        )
        self.assertIn("etf_flows_support_buy",out["reasons"])
        self.assertGreater(out["score"],0)



if __name__=="__main__":
    unittest.main()
