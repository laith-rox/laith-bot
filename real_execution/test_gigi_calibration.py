import unittest

import gigi_calibration


class GigiCalibrationTests(unittest.TestCase):
    def test_small_sample_is_not_calibrated(self):
        out = gigi_calibration.calibrate_bucket({"n":10,"wins":7,"sum_r":3.0})
        self.assertEqual(out["status"],"INSUFFICIENT_SAMPLE")
        self.assertEqual(out["n"],10)

    def test_large_balanced_sample_has_interval(self):
        out = gigi_calibration.calibrate_bucket({"n":100,"wins":60,"sum_r":20.0})
        self.assertEqual(out["status"],"CALIBRATED_EMPIRICAL")
        self.assertLess(out["wilson_low"],0.60)
        self.assertGreater(out["wilson_high"],0.60)
        self.assertAlmostEqual(out["mean_r"],0.2,places=4)

    def test_zero_sample_does_not_fake_rate(self):
        out = gigi_calibration.calibrate_bucket({})
        self.assertIsNone(out["empirical_positive_rate"])
        self.assertEqual(out["wilson_low"],0.0)
        self.assertEqual(out["wilson_high"],1.0)

    def test_report_filters_dimensions(self):
        state={
            "resolved":100,
            "buckets":{
                "alignment:SUPPORT":{"n":50,"wins":30,"sum_r":10},
                "mode:MAIN":{"n":50,"wins":30,"sum_r":10},
            },
        }
        out=gigi_calibration.report(state,("alignment",))
        self.assertIn("alignment:SUPPORT",out["buckets"])
        self.assertNotIn("mode:MAIN",out["buckets"])


if __name__=="__main__":
    unittest.main()
