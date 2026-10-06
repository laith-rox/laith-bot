import unittest

import gigi_slice_proof


class GigiSliceProofTests(unittest.TestCase):
    def test_sniper_is_persistently_negative_across_slice_dimensions(self):
        out = gigi_slice_proof.assess(
            "SNIPER","BUY","2026-10-01T07:30:00Z",6,"UP"
        )
        self.assertEqual(out["posture"],"PERSISTENT_NEGATIVE_SLICE")
        self.assertEqual(out["session_proof"]["status"],"STABLE_NEGATIVE")
        self.assertEqual(out["strength_proof"]["status"],"STABLE_NEGATIVE")
        self.assertEqual(out["h4_proof"]["status"],"STABLE_NEGATIVE")

    def test_main_london_is_promising_but_not_called_proven(self):
        out = gigi_slice_proof.assess(
            "MAIN","BUY","2026-10-01T07:30:00Z",7,"UP"
        )
        self.assertEqual(out["session_proof"]["key"],"MAIN|LONDON_10_13")
        self.assertEqual(out["session_proof"]["status"],"UNSTABLE")
        self.assertGreater(out["session_proof"]["mean_r"],0)
        self.assertNotIn("PROVEN",out["posture"])

    def test_us_main_negative_average_stays_unproven_not_fake_short_signal(self):
        out = gigi_slice_proof.assess(
            "MAIN","SELL","2026-10-01T13:00:00Z",6,"DOWN"
        )
        self.assertEqual(out["session_proof"]["key"],"MAIN|US_1520_18")
        self.assertLess(out["session_proof"]["mean_r"],0)
        self.assertFalse(out["directional_signal"])
        self.assertFalse(out["execution_gate"])

    def test_clock_is_dst_aware_through_shared_clock(self):
        bucket = gigi_slice_proof.session_bucket("2026-10-01T07:00:00Z")
        self.assertEqual(bucket,"LONDON_10_13")


if __name__=="__main__":
    unittest.main()
