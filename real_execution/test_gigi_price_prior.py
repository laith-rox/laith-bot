import unittest

import gigi_price_prior


class GigiPricePriorTests(unittest.TestCase):
    def test_known_positive_reason_is_visible(self):
        out=gigi_price_prior.assess("m15_support_break_retest")
        self.assertEqual(out["status"],"STABLE_POSITIVE")
        self.assertGreater(out["total_n"],100)
        self.assertFalse(out["execution_gate"])

    def test_known_negative_reason_is_visible(self):
        out=gigi_price_prior.assess("fast_primary_2of3")
        self.assertEqual(out["status"],"STABLE_NEGATIVE")
        self.assertLess(out["mean_r_across_windows"],0)
        self.assertFalse(out["directional_signal"])

    def test_unknown_reason_is_not_invented(self):
        out=gigi_price_prior.assess("new_future_setup")
        self.assertEqual(out["status"],"UNQUALIFIED_OR_UNKNOWN")
        self.assertFalse(out["execution_gate"])


if __name__=="__main__":
    unittest.main()
