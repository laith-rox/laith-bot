import unittest

import gigi_thesis


class GigiThesisTests(unittest.TestCase):
    def test_clean_buy_requires_cross_family_support(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"UP"},
            {"bias":"BULLISH_GOLD"},
            {"regime":"CLEAR"},
            {"pressure":"BULLISH"},
            {"regime":"LONG_BIASED_ADDING"},
            {"regime":"BROAD_INFLOW"},
            {"dominant_risk":"BALANCED"},
            {"skew":"BALANCED"},
        )
        self.assertEqual(out["state"],"CLEAN")
        self.assertGreaterEqual(out["support_count"],3)
        self.assertEqual(out["conflict_count"],0)

    def test_two_independent_conflicts_make_thesis_fragile(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"DOWN"},
            {"bias":"BEARISH_GOLD"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            {"regime":"NEUTRAL"},
            {"regime":"MIXED"},
            {"dominant_risk":"BALANCED"},
            {"skew":"BALANCED"},
        )
        self.assertEqual(out["state"],"FRAGILE")
        self.assertGreaterEqual(out["conflict_count"],2)

    def test_missing_invalidation_is_fragile(self):
        out=gigi_thesis.audit({"side":"SELL","risk_distance":0})
        self.assertEqual(out["state"],"FRAGILE")
        self.assertIn("invalidation_missing",out["conflicts"])

    def test_event_uncertainty_is_not_fake_directional_conflict(self):
        out=gigi_thesis.audit(
            {"side":"SELL","risk_distance":2.0},
            {"h4_bias":"DOWN"},
            {"bias":"NEUTRAL"},
            {"regime":"HIGH_IMPACT_WINDOW"},
        )
        self.assertIn("high_impact_event_window",out["uncertainty"])
        self.assertNotIn("high_impact_event_window",out["conflicts"])

    def test_related_flow_evidence_counts_as_one_family(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"NEUTRAL"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            {"regime":"LONG_BIASED_ADDING"},
            {"regime":"BROAD_INFLOW"},
            {"dominant_risk":"BALANCED"},
            {"skew":"UPSIDE_CALL_BID"},
        )
        self.assertIn("flows",out["support_families"])
        self.assertEqual(out["support_count"],1)
        self.assertEqual(out["state"],"UNPROVEN")


    def test_low_external_data_quality_is_uncertainty_not_direction(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"UP"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            quality={"quality":"LOW"},
        )
        self.assertIn("external_context_low_quality",out["uncertainty"])
        self.assertNotIn("external_context_low_quality",out["conflicts"])


    def test_wide_broker_spread_is_uncertainty_not_direction(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"UP"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            execution_quality={"quality":"WIDE"},
        )
        self.assertIn("broker_spread_wide",out["uncertainty"])
        self.assertNotIn("broker_spread_wide",out["conflicts"])


    def test_same_direction_stacking_is_uncertainty_not_block(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"UP"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            exposure={"stacking_state":"HIGH_CONCENTRATION","book_state":"SAME_DIRECTION"},
        )
        self.assertIn("same_direction_exposure_high",out["uncertainty"])
        self.assertNotIn("same_direction_exposure_high",out["conflicts"])


    def test_flipping_intermarket_relationship_is_uncertainty(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"UP"},
            {"bias":"NEUTRAL","relationship_state":"FLIPPING_PRESENT"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
        )
        self.assertIn("intermarket_relationship_flipping",out["uncertainty"])
        self.assertNotIn("intermarket_relationship_flipping",out["conflicts"])

    def test_options_convexity_is_uncertainty_not_direction(self):
        out=gigi_thesis.audit(
            {"side":"SELL","risk_distance":3.0},
            {"h4_bias":"DOWN"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            options={
                "skew":"BALANCED",
                "oi_state":"CALL_HEAVY",
                "gross_gamma_oi_context":"MODERATE_NEAR_SPOT_CONVEXITY",
            },
        )
        self.assertIn("options_call_oi_heavy",out["uncertainty"])
        self.assertIn("options_near_spot_convexity_moderate",out["uncertainty"])
        self.assertNotIn("options_call_oi_heavy",out["conflicts"])



if __name__=="__main__":
    unittest.main()
