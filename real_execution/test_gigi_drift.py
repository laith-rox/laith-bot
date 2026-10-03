import unittest

import gigi_drift


class GigiDriftTests(unittest.TestCase):
    def test_small_sample_is_not_trusted(self):
        out=gigi_drift.detect_values([0.2]*20)
        self.assertEqual(out["status"],"INSUFFICIENT_DRIFT_SAMPLE")
        self.assertFalse(out["shadow_trust"])

    def test_sign_flip_is_detected(self):
        vals=[0.5]*35+[-0.5]*15
        out=gigi_drift.detect_values(vals)
        self.assertEqual(out["status"],"SIGN_FLIP")
        self.assertFalse(out["shadow_trust"])

    def test_stable_positive_edge_is_trusted(self):
        vals=[0.35]*35+[0.30]*15
        out=gigi_drift.detect_values(vals)
        self.assertEqual(out["status"],"STABLE")
        self.assertTrue(out["shadow_trust"])

    def test_report_is_bucketed_chronologically(self):
        obs=[]
        for i in range(50):
            obs.append({"resolved_at":i,"close_r":0.2,"mode":"MAIN"})
        out=gigi_drift.report(obs,["mode"])
        self.assertIn("mode:MAIN",out["buckets"])


if __name__=="__main__":
    unittest.main()
