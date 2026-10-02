from datetime import datetime, timedelta, timezone
import unittest

from gigi_gold_brain import GigiGoldBrain
from market import Bar

UTC = timezone.utc


def b(dt, o, h, l, c):
    return Bar(dt, o, h, l, c)


class GigiGoldBrainStoryTests(unittest.TestCase):
    def test_new_york_rollover_defines_gold_day(self):
        before = datetime(2026, 10, 2, 20, 55, tzinfo=UTC)  # 16:55 NY
        after = datetime(2026, 10, 2, 21, 5, tzinfo=UTC)    # 17:05 NY
        self.assertNotEqual(
            GigiGoldBrain._trading_day(before),
            GigiGoldBrain._trading_day(after),
        )

    def test_bullish_engulfing_is_detected(self):
        start = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
        bars = [
            b(start, 100, 101, 97, 98),
            b(start + timedelta(minutes=5), 97.5, 102, 97, 101.5),
        ]
        story = GigiGoldBrain._candle_story(bars)
        self.assertEqual(story["lastPattern"], "BULL_ENGULFING")

    def test_previous_high_sweep_and_rejection(self):
        start = datetime(2026, 10, 1, 21, 0, tzinfo=UTC)
        bars = []
        # Prior trading day: 100-110.
        for i in range(12):
            bars.append(b(start + timedelta(minutes=5*i), 104, 110, 100, 105))
        # Current trading day trades above 110, then closes back below.
        current = start + timedelta(days=1)
        bars += [
            b(current, 105, 111.5, 104, 109),
            b(current + timedelta(minutes=5), 109, 110, 106, 108),
        ]
        story = GigiGoldBrain._daily_story(
            bars, current + timedelta(minutes=15)
        )
        self.assertTrue(story["sweptPreviousHigh"])
        self.assertEqual(story["event"], "HIGH_SWEEP_REJECTION")
        self.assertEqual(story["directionalHint"], "SELL")


if __name__ == "__main__":
    unittest.main()
