import unittest

import gigi_benchmark


class GigiBenchmarkTests(unittest.TestCase):
    def test_am_pre_window_is_dst_aware(self):
        # 2026-10-02 London is BST (UTC+1): 09:20 UTC == 10:20 London.
        out = gigi_benchmark.context("2026-10-02T09:20:00Z")
        self.assertEqual(out["nearest_auction"], "LBMA_AM")
        self.assertEqual(out["phase"], "PRE_AUCTION")
        self.assertEqual(out["minutes_from_auction"], -10)

    def test_am_auction_window(self):
        out = gigi_benchmark.context("2026-10-02T09:30:00Z")
        self.assertEqual(out["nearest_auction"], "LBMA_AM")
        self.assertEqual(out["phase"], "AUCTION_OR_IMMEDIATE_POST")

    def test_pm_window(self):
        # 14:05 UTC == 15:05 London in BST.
        out = gigi_benchmark.context("2026-10-02T14:05:00Z")
        self.assertEqual(out["nearest_auction"], "LBMA_PM")
        self.assertEqual(out["phase"], "AUCTION_OR_IMMEDIATE_POST")

    def test_outside_window_is_nondirectional(self):
        out = gigi_benchmark.context("2026-10-02T12:00:00Z")
        self.assertEqual(out["phase"], "OUTSIDE_AUCTION_WINDOW")
        self.assertFalse(out["directional_signal"])


if __name__ == "__main__":
    unittest.main()
