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


    def test_liquidation_risk_is_exposed_without_changing_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"MIXED"},
            {"dominant_risk":"WATCH_LONG_LIQUIDATION"},
        )
        self.assertEqual(out["crowding_risk"],"WATCH_LONG_LIQUIDATION")
        self.assertIn("long_liquidation_risk",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_options_skew_is_exposed_without_direct_score_change(self):
        out=gigi_context.evaluate(
            "SELL",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"MIXED"},
            {"dominant_risk":"BALANCED"},
            {"skew":"DOWNSIDE_HEDGE_BID","oi_state":"PUT_HEAVY"},
        )
        self.assertEqual(out["options_skew"],"DOWNSIDE_HEDGE_BID")
        self.assertIn("options_downside_hedge_bid",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_options_convexity_is_exposed_without_direction_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"MIXED"},
            {"dominant_risk":"BALANCED"},
            {"skew":"BALANCED","oi_state":"BALANCED","gross_gamma_oi_context":"HIGH_NEAR_SPOT_CONVEXITY"},
        )
        self.assertEqual(out["options_gamma_context"],"HIGH_NEAR_SPOT_CONVEXITY")
        self.assertIn("options_high_near_spot_convexity",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_related_positioning_and_etf_only_count_once(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"LONG_BIASED_ADDING","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"BROAD_INFLOW"},
            {"dominant_risk":"BALANCED"},
            {"skew":"BALANCED","oi_state":"BALANCED"},
            {"real_yield_regime":"STABLE_REAL_YIELD","policy_regime":"STABLE_FRONT_END"},
        )
        self.assertEqual(out["flow_family_score"],1)
        self.assertEqual(out["score"],1)
        self.assertIn("positioning_supports_buy",out["reasons"])
        self.assertIn("etf_flows_support_buy",out["reasons"])

    def test_conflicting_flow_evidence_cancels_family_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"LONG_BIASED_ADDING","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"BROAD_OUTFLOW"},
            {"dominant_risk":"BALANCED"},
            {"skew":"BALANCED","oi_state":"BALANCED"},
            {"real_yield_regime":"STABLE_REAL_YIELD","policy_regime":"STABLE_FRONT_END"},
        )
        self.assertEqual(out["flow_family_score"],0)
        self.assertEqual(out["score"],0)
        self.assertIn("flow_family_mixed",out["reasons"])


    def test_event_reversal_is_exposed_without_fake_direction_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"NORMAL"},
            {"regime":"MIXED"},
            {"dominant_risk":"BALANCED"},
            {"skew":"BALANCED","oi_state":"BALANCED"},
            {"real_yield_regime":"STABLE_REAL_YIELD","policy_regime":"STABLE_FRONT_END"},
            {"state":"SHOCK_REVERSED","impulse":"BULLISH"},
        )
        self.assertEqual(out["event_response_state"],"SHOCK_REVERSED")
        self.assertIn("event_shock_reversed",out["reasons"])
        self.assertEqual(out["score"],0)



if __name__=="__main__":
    unittest.main()
