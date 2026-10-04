import unittest
import gigi_release_gate


class GigiReleaseGateTests(unittest.TestCase):
    def test_stable_negative_mode_is_hold(self):
        out=gigi_release_gate.assess({
            "mode_status":"STABLE_NEGATIVE","reason_status":"UNQUALIFIED_OR_UNKNOWN",
            "mode_total_n":1000,"mode_weighted_mean_r":-0.1,
        })
        self.assertEqual(out["state"],"RESEARCH_HOLD")
        self.assertFalse(out["authorizes_execution"])

    def test_promising_but_unstable_stays_shadow(self):
        out=gigi_release_gate.assess({
            "mode_status":"PROMISING_UNSTABLE","reason_status":"UNQUALIFIED_OR_UNKNOWN",
            "mode_total_n":1200,"mode_weighted_mean_r":0.05,
        })
        self.assertEqual(out["state"],"SHADOW_ONLY")

    def test_even_stable_mode_needs_stable_setup_reason(self):
        out=gigi_release_gate.assess({
            "mode_status":"STABLE_POSITIVE","reason_status":"UNQUALIFIED_OR_UNKNOWN",
            "mode_total_n":500,"mode_weighted_mean_r":0.08,
        })
        self.assertEqual(out["state"],"SHADOW_ONLY")

    def test_strong_research_evidence_still_does_not_authorize_execution(self):
        out=gigi_release_gate.assess({
            "mode_status":"STABLE_POSITIVE","reason_status":"STABLE_POSITIVE",
            "mode_total_n":500,"mode_weighted_mean_r":0.08,
        })
        self.assertEqual(out["state"],"EVIDENCE_CANDIDATE")
        self.assertFalse(out["authorizes_execution"])
        self.assertFalse(out["execution_gate"])


if __name__=="__main__":
    unittest.main()
