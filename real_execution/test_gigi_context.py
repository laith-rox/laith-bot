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


    def test_session_vwap_and_failed_break_are_context_only(self):
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
            {"state":"NO_ACTIVE_HIGH_EVENT","impulse":"NONE"},
            {
                "vwap_relation":"ABOVE_ACCEPTANCE",
                "extension_state":"EXTENDED",
                "range_event":"FAILED_BREAK_ABOVE",
            },
        )
        self.assertEqual(out["session_vwap_relation"],"ABOVE_ACCEPTANCE")
        self.assertEqual(out["session_extension"],"EXTENDED")
        self.assertEqual(out["session_range_event"],"FAILED_BREAK_ABOVE")
        self.assertIn("session_vwap_above_acceptance",out["reasons"])
        self.assertIn("session_failed_break_above",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_options_backwardation_is_context_only(self):
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
            {"skew":"BALANCED","oi_state":"BALANCED","term_structure":"BACKWARDATION"},
        )
        self.assertEqual(out["options_term_structure"],"BACKWARDATION")
        self.assertIn("options_near_term_vol_premium",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_lbma_benchmark_window_is_context_only(self):
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
            {"state":"NO_ACTIVE_HIGH_EVENT","impulse":"NONE"},
            {"vwap_relation":"CROSSING","extension_state":"FAIR_VALUE_ZONE","range_event":"INSIDE"},
            {"phase":"AUCTION_OR_IMMEDIATE_POST","nearest_auction":"LBMA_AM"},
        )
        self.assertEqual(out["benchmark_phase"],"AUCTION_OR_IMMEDIATE_POST")
        self.assertEqual(out["nearest_benchmark"],"LBMA_AM")
        self.assertIn("lbma_benchmark_auction_window",out["reasons"])


    def test_target_geometry_is_context_only(self):
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
            {"state":"NO_ACTIVE_HIGH_EVENT","impulse":"NONE"},
            {"vwap_relation":"CROSSING","extension_state":"FAIR_VALUE_ZONE","range_event":"INSIDE"},
            {"phase":"OUTSIDE_AUCTION_WINDOW","nearest_auction":"LBMA_AM"},
            {"state":"AMBITION_HIGH","implied_move_relation":"FAR_BEYOND_1D_PROXY"},
        )
        self.assertEqual(out["target_geometry_state"],"AMBITION_HIGH")
        self.assertEqual(out["target_implied_relation"],"FAR_BEYOND_1D_PROXY")
        self.assertIn("target_ambition_high",out["reasons"])
        self.assertIn("target_far_beyond_options_1d_proxy",out["reasons"])


    def test_options_skew_is_visible_but_not_directional_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},{"regime":"CLEAR"},
            {"event":"NONE","pressure":"NEUTRAL"},
            {"regime":"NEUTRAL","crowding":"NORMAL"},
            {"state":"NORMAL"},{"regime":"MIXED"},{"dominant_risk":"BALANCED"},
            {"skew":"DOWNSIDE_HEDGE_BID","oi_state":"PUT_HEAVY"},
        )
        self.assertEqual(out["options_skew"],"DOWNSIDE_HEDGE_BID")
        self.assertIn("options_downside_hedge_bid",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_multi_high_macro_bundle_is_visible_not_fake_direction(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"HIGH_IMPACT_WINDOW","phase":"PRE_HIGH_EVENT","event_bundle_state":"MULTI_HIGH_RELEASE"},
        )
        self.assertEqual(out["macro_event_bundle"],"MULTI_HIGH_RELEASE")
        self.assertIn("macro_multi_high_release_bundle",out["reasons"])

    def test_options_reasons_are_not_duplicated(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            options={"skew":"DOWNSIDE_HEDGE_BID","oi_state":"PUT_HEAVY"},
        )
        self.assertEqual(out["reasons"].count("options_downside_hedge_bid"),1)
        self.assertEqual(out["reasons"].count("options_put_oi_heavy"),1)


    def test_local_premium_is_visible_but_not_directional_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            local_premium={
                "china":{"state":"STRONG_PREMIUM"},
                "india":{"state":"DISCOUNT"},
            },
        )
        self.assertEqual(out["china_local_premium_state"],"STRONG_PREMIUM")
        self.assertIn("china_local_premium_strong",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_synthetic_usd_is_visible_without_direct_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            usd_basket={"state":"USD_STRONG_IMPULSE","breadth":0.82},
        )
        self.assertEqual(out["synthetic_usd_state"],"USD_STRONG_IMPULSE")
        self.assertIn("synthetic_usd_strong_impulse",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_gold_usd_relationship_flip_is_visible_without_score_change(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            usd_basket={
                "state":"USD_MIXED",
                "breadth":0.70,
                "gold_relationship":{"state":"RELATIONSHIP_FLIP"},
            },
        )
        self.assertEqual(out["synthetic_usd_relationship"],"RELATIONSHIP_FLIP")
        self.assertIn("gold_usd_relationship_flip",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_near_expiry_oi_cluster_is_context_only(self):
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
            {"near_expiry_pin_state":"NEAR_EXPIRY_OI_CLUSTER_AT_SPOT"},
        )
        self.assertEqual(out["options_expiry_pin_state"],"NEAR_EXPIRY_OI_CLUSTER_AT_SPOT")
        self.assertIn("options_near_expiry_oi_cluster_at_spot",out["reasons"])
        self.assertEqual(out["score"],0)


    def test_central_bank_buying_is_visible_but_not_directional_score(self):
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
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {"regime":"NET_BUYING","monthly_net_tonnes":23.0},
        )
        self.assertEqual(out["central_bank_regime"],"NET_BUYING")
        self.assertIn("central_bank_net_buying_backdrop",out["reasons"])
        self.assertEqual(out["score"],0)



if __name__=="__main__":
    unittest.main()
