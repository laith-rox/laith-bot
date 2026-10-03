import unittest

import gigi_behavior


class GigiBehaviorTests(unittest.TestCase):
    def signal(self, side="BUY", strength=7):
        checks=[True]*strength+[False]*(7-strength)
        return {"side":side,"checks":{side:checks}}

    def test_strong_technical_score_with_fragile_thesis_flags_confirmation_bias(self):
        out=gigi_behavior.assess(
            self.signal(strength=7),
            {"alignment":"SUPPORT","reasons":[]},
            {"state":"FRAGILE","conflict_count":2},
        )
        self.assertIn("confirmation_bias_risk",out["flags"])
        self.assertFalse(out["execution_gate"])

    def test_news_first_spike_chasing_is_flagged(self):
        out=gigi_behavior.assess(
            self.signal(strength=5),
            {"alignment":"MIXED","reasons":["first_spike_untrusted"]},
            {"state":"UNPROVEN","conflict_count":0},
        )
        self.assertIn("news_first_spike_chase_risk",out["flags"])

    def test_multiple_positions_with_weak_context_flags_overtrading(self):
        out=gigi_behavior.assess(
            self.signal(strength=5),
            {"alignment":"MIXED","reasons":[]},
            {"state":"MIXED","conflict_count":1},
            {"stacking_state":"HIGH_CONCENTRATION"},
        )
        self.assertIn("overtrading_concentration_risk",out["flags"])

    def test_clean_setup_stays_clean(self):
        out=gigi_behavior.assess(
            self.signal(strength=6),
            {"alignment":"STRONG_SUPPORT","reasons":[]},
            {"state":"CLEAN","conflict_count":0},
            {"stacking_state":"CLEAR"},
            {"noise_exposure":"LOW"},
        )
        self.assertEqual(out["state"],"CLEAN")


if __name__=="__main__":
    unittest.main()
