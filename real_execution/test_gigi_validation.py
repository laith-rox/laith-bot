import unittest

import gigi_validation


class GigiValidationTests(unittest.TestCase):
    def test_small_sample_is_never_promoted(self):
        out=gigi_validation.validate_values([1.0]*20)
        self.assertEqual(out["status"],"INSUFFICIENT_OUT_OF_SAMPLE")
        self.assertFalse(out["shadow_candidate"])

    def test_positive_train_and_test_is_stable(self):
        values=[0.8,-0.2,1.1,0.4]*12
        out=gigi_validation.validate_values(values)
        self.assertEqual(out["status"],"STABLE_POSITIVE")
        self.assertTrue(out["shadow_candidate"])
        self.assertGreater(out["test_mean_r"],0)

    def test_sign_flip_is_unstable(self):
        values=[1.0]*30 + [-1.0]*20
        out=gigi_validation.validate_values(values)
        self.assertEqual(out["status"],"UNSTABLE_SIGN_FLIP")
        self.assertFalse(out["shadow_candidate"])

    def test_large_outlier_is_clipped(self):
        values=[0.2]*39 + [1000.0]
        out=gigi_validation.validate_values(values)
        self.assertLessEqual(out["test_mean_r"],gigi_validation.CLIP_R)

    def test_report_is_chronological_and_bucketed(self):
        obs=[]
        for i in range(45):
            obs.append({
                "resolved_at":i,
                "close_r":0.5 if i%3 else -0.2,
                "mode":"SNIPER",
                "regime":"TREND_UP",
            })
        out=gigi_validation.report(obs,("mode","regime"))
        self.assertIn("mode:SNIPER",out["buckets"])
        self.assertIn("regime:TREND_UP",out["buckets"])
        self.assertEqual(out["resolved_observations"],45)


if __name__=="__main__":
    unittest.main()
