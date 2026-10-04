import unittest

import gigi_evidence


class GigiEvidenceTests(unittest.TestCase):
    def test_correlated_macro_inputs_collapse_to_one_family_vote(self):
        out=gigi_evidence.audit(
            "BUY",
            yields={"real_yield_regime":"FALLING_REAL_YIELD"},
            usd_basket={"state":"USD_SOFT"},
            macro_surprise={"bundle_surprise":"USD_NEGATIVE"},
        )
        self.assertEqual(out["families"]["MACRO_POLICY"],1)
        self.assertEqual(out["independent_support_count"],1)

    def test_flow_inputs_collapse_to_one_family_vote(self):
        out=gigi_evidence.audit(
            "SELL",
            positioning={"regime":"LONG_BIASED_DELEVERAGING"},
            etf={"regime":"BROAD_OUTFLOW"},
            crowding={"dominant_risk":"WATCH_LONG_LIQUIDATION"},
        )
        self.assertEqual(out["families"]["FLOWS_POSITIONING"],1)
        self.assertEqual(out["independent_support_count"],1)

    def test_major_contradiction_is_detected(self):
        out=gigi_evidence.audit(
            "BUY",
            regime={"h4_bias":"UP"},
            liquidity={"pressure":"BULLISH"},
            session_profile={"vwap_relation":"ABOVE_ACCEPTANCE"},
            yields={"real_yield_regime":"RISING_REAL_YIELD"},
            usd_basket={"state":"USD_STRONG_IMPULSE"},
            macro_surprise={"bundle_surprise":"USD_POSITIVE"},
            positioning={"regime":"LONG_BIASED_ADDING"},
            etf={"regime":"BROAD_INFLOW"},
            options={"skew":"DOWNSIDE_HEDGE_BID","oi_state":"PUT_HEAVY"},
            volatility={"state":"NORMAL"},
            intermarket={"bias":"BEARISH_GOLD"},
            local_premium={"china":{"state":"DISCOUNT"},"india":{"state":"DISCOUNT"}},
        )
        self.assertEqual(out["state"],"MAJOR_CONTRADICTION")
        self.assertGreaterEqual(out["independent_support_count"],2)
        self.assertGreaterEqual(out["independent_conflict_count"],2)

    def test_raw_options_oi_is_unsigned_not_directional(self):
        buy=gigi_evidence.audit(
            "BUY",
            options={"skew":"BALANCED","oi_state":"CALL_HEAVY"},
            volatility={"state":"NORMAL"},
        )
        sell=gigi_evidence.audit(
            "SELL",
            options={"skew":"BALANCED","oi_state":"PUT_HEAVY"},
            volatility={"state":"NORMAL"},
        )
        self.assertEqual(buy["families"]["OPTIONS_VOLATILITY"],0)
        self.assertEqual(sell["families"]["OPTIONS_VOLATILITY"],0)


    def test_audit_is_not_entry_signal(self):
        out=gigi_evidence.audit("BUY")
        self.assertTrue(out["correlated_inputs_collapsed"])
        self.assertIn("not_probability_or_entry_signal",out["note"])

    def test_many_correlated_inputs_cannot_fake_many_independent_votes(self):
        out=gigi_evidence.audit(
            "BUY",
            positioning={"regime":"LONG_BIASED_ADDING"},
            etf={"regime":"BROAD_INFLOW"},
            crowding={"dominant_risk":"HIGH_SHORT_SQUEEZE"},
            options={"skew":"BALANCED","oi_state":"CALL_HEAVY"},
            volatility={"state":"STRESS_EXPANSION"},
        )
        self.assertEqual(out["families"]["FLOWS_POSITIONING"],1)
        self.assertEqual(out["families"]["OPTIONS_VOLATILITY"],0)
        self.assertEqual(out["independent_support_count"],1)

    def test_all_families_are_hard_capped_at_five(self):
        out=gigi_evidence.audit(
            "BUY",
            regime={"h4_bias":"UP"},
            liquidity={"pressure":"BULLISH"},
            session_profile={"vwap_relation":"ABOVE_ACCEPTANCE"},
            yields={"real_yield_regime":"FALLING_REAL_YIELD"},
            usd_basket={"state":"USD_SOFT"},
            macro_surprise={"bundle_surprise":"USD_NEGATIVE"},
            positioning={"regime":"LONG_BIASED_ADDING"},
            etf={"regime":"BROAD_INFLOW"},
            crowding={"dominant_risk":"HIGH_SHORT_SQUEEZE"},
            options={"skew":"UPSIDE_CALL_BID","oi_state":"CALL_HEAVY"},
            volatility={"state":"STRESS_EXPANSION"},
            intermarket={"bias":"BULLISH_GOLD"},
            local_premium={"china":{"state":"PREMIUM"},"india":{"state":"PREMIUM"}},
        )
        self.assertEqual(set(out["families"]),{
            "PRICE_STRUCTURE","MACRO_POLICY","FLOWS_POSITIONING",
            "OPTIONS_VOLATILITY","CROSS_MARKET_PHYSICAL",
        })
        self.assertLessEqual(out["independent_support_count"],5)
        self.assertLessEqual(out["active_family_count"],5)



if __name__=="__main__":
    unittest.main()
