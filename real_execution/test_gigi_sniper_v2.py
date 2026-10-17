import unittest

import gigi_sniper_v2


def base_signal(side="BUY"):
    return {
        "side":side,
        "risk_distance":4.0,
        "regime":{"h4_bias":"UP" if side=="BUY" else "DOWN"},
        "checks":{side:[True,True,True,True,True,True,False]},
    }


class GigiSniperV2Tests(unittest.TestCase):
    def test_liquidity_reversal_low_cost_can_be_shadow_candidate(self):
        out=gigi_sniper_v2.assess(
            base_signal(),
            {"primary":"LIQUIDITY_REVERSAL","primary_score":6},
            {"quality":"NORMAL","spread_usd":0.16},
            {"noise_exposure":"LOW"},
            {"state":"NORMAL_UNCERTAINTY"},
            {"state":"BROAD_SUPPORT","independent_support_count":3,"independent_conflict_count":0},
            {"phase":"NORMAL"},
            {"status":"UNQUALIFIED_OR_UNKNOWN"},
            {"state":"SHADOW_REVIEW"},
        )
        self.assertIn(out["state"],("SHADOW_CANDIDATE","STRONG_SHADOW_CANDIDATE"))
        self.assertLessEqual(out["spread_to_risk"],0.05)
        self.assertFalse(out["authorizes_execution"])

    def test_legacy_negative_reason_is_rejected(self):
        out=gigi_sniper_v2.assess(
            base_signal(),
            {"primary":"LIQUIDITY_REVERSAL","primary_score":6},
            {"quality":"NORMAL","spread_usd":0.10},
            {"noise_exposure":"LOW"},
            {"state":"NORMAL_UNCERTAINTY"},
            {"state":"BROAD_SUPPORT","independent_support_count":3,"independent_conflict_count":0},
            {"phase":"NORMAL"},
            {"status":"STABLE_NEGATIVE"},
            {"state":"SHADOW_REVIEW"},
        )
        self.assertEqual(out["state"],"REJECT")
        self.assertIn("legacy_reason_stable_negative",out["blockers"])

    def test_first_news_spike_is_rejected(self):
        out=gigi_sniper_v2.assess(
            base_signal(),
            {"primary":"BREAKOUT_ACCEPTANCE","primary_score":5},
            {"quality":"NORMAL","spread_usd":0.10},
            {"noise_exposure":"LOW"},
            {"state":"NORMAL_UNCERTAINTY"},
            {"state":"LEAN_SUPPORT","independent_support_count":2,"independent_conflict_count":0},
            {"phase":"HIGH_EVENT_SHOCK_0_5M"},
            {"status":"UNQUALIFIED_OR_UNKNOWN"},
            {"state":"SHADOW_REVIEW"},
        )
        self.assertEqual(out["state"],"REJECT")
        self.assertIn("event_first_move_untrusted",out["blockers"])

    def test_cost_above_eight_percent_of_risk_is_rejected(self):
        out=gigi_sniper_v2.assess(
            base_signal(),
            {"primary":"LIQUIDITY_REVERSAL","primary_score":6},
            {"quality":"NORMAL","spread_usd":0.40},
            {"noise_exposure":"LOW"},
            {"state":"NORMAL_UNCERTAINTY"},
            {"state":"BROAD_SUPPORT","independent_support_count":3,"independent_conflict_count":0},
            {"phase":"NORMAL"},
            {"status":"UNQUALIFIED_OR_UNKNOWN"},
            {"state":"SHADOW_REVIEW"},
        )
        self.assertEqual(out["state"],"REJECT")
        self.assertEqual(out["cost_bucket"],"GT_0_08R")

    def test_trend_continuation_not_repackaged_as_new_sniper(self):
        out=gigi_sniper_v2.assess(
            base_signal(),
            {"primary":"TREND_CONTINUATION","primary_score":7},
            {"quality":"NORMAL","spread_usd":0.10},
            {"noise_exposure":"LOW"},
            {"state":"NORMAL_UNCERTAINTY"},
            {"state":"BROAD_SUPPORT","independent_support_count":4,"independent_conflict_count":0},
            {"phase":"NORMAL"},
            {"status":"UNQUALIFIED_OR_UNKNOWN"},
            {"state":"SHADOW_CLEAN"},
        )
        self.assertEqual(out["state"],"REJECT")
        self.assertIn("legacy_or_undifferentiated_archetype",out["blockers"])


if __name__=="__main__":
    unittest.main()
