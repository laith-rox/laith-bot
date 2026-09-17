import unittest

from v4_quick_balance import timing_block


class V4QuickCandleTimingTests(unittest.TestCase):
    def test_aligned_trade_shows_same_local_candle_and_trade_slot_time(self):
        # 2026-09-17 18:45:00 UTC = 21:45:00 Asia/Hebron.
        trade = {
            "timing_aligned": True,
            "candle_start": 1789670700.0,
            "entry_delay_seconds": 12.4,
            "candle_open": 4302.20,
        }
        lines = timing_block(trade)
        text = "\n".join(lines)
        self.assertIn("21:45:00", text)
        self.assertEqual(text.count("21:45:00"), 2)
        self.assertIn("12ث", text)
        self.assertIn("4302.20", text)
        self.assertIn("مطابق للشمعة", text)

    def test_unaligned_trade_does_not_claim_timing_match(self):
        self.assertEqual(timing_block({"timing_aligned": False, "candle_start": 1789670700.0}), [])


if __name__ == "__main__":
    unittest.main()
