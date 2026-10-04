import unittest
import gigi_uncertainty


class GigiUncertaintyTests(unittest.TestCase):
    def test_conflicted_low_quality_event_can_abstain(self):
        out=gigi_uncertainty.assess(
            {"side":"BUY"},
            {"alignment":"CONFLICT"},
            {"state":"CONTRADICTED","support_count":2,"conflict_count":3},
            {"quality":"LOW"},
            {"regime":"HIGH_IMPACT_WINDOW","phase":"HIGH_EVENT_SHOCK_0_5M"},
            {"name":"VOLATILE_TRANSITION"},
        )
        self.assertEqual(out["state"],"HIGH_UNCERTAINTY")
        self.assertEqual(out["posture"],"ABSTAIN_SHADOW")
        self.assertFalse(out["execution_gate"])

    def test_clean_aligned_context_stays_normal(self):
        out=gigi_uncertainty.assess(
            {"side":"SELL"},
            {"alignment":"SUPPORT"},
            {"state":"SUPPORTED","support_count":4,"conflict_count":0},
            {"quality":"HIGH"},
            {"regime":"CLEAR","phase":"NORMAL"},
            {"name":"TREND_DOWN"},
        )
        self.assertEqual(out["state"],"NORMAL_UNCERTAINTY")
        self.assertEqual(out["posture"],"NORMAL_ANALYSIS")

    def test_mixed_context_reduces_confidence_without_auto_block(self):
        out=gigi_uncertainty.assess(
            {"side":"BUY"},
            {"alignment":"MIXED"},
            {"state":"MIXED","support_count":2,"conflict_count":1},
            {"quality":"MEDIUM"},
            {"regime":"CLEAR","phase":"NORMAL"},
            {"name":"RANGE"},
        )
        self.assertEqual(out["state"],"ELEVATED_UNCERTAINTY")
        self.assertEqual(out["posture"],"REDUCE_CONFIDENCE")
        self.assertFalse(out["execution_gate"])


if __name__=="__main__":
    unittest.main()
