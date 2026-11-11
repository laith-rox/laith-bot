import unittest
from datetime import datetime, timezone, timedelta
from market import Bar, DataError, require_fresh
from v4_schedule import next_official_cycle


class V4ScheduleTests(unittest.TestCase):
    def test_logged_drift_rejected_but_aligned_cycle_is_fresh(self):
        now = datetime(2026, 11, 11, 15, 27, 54, tzinfo=timezone.utc)
        last = Bar(now.replace(minute=20, second=0), 4010, 4012, 4008, 4009, 5)
        with self.assertRaisesRegex(DataError, "market_closed_candles_stale"):
            require_fresh([last], now, 120)
        target = datetime.fromtimestamp(next_official_cycle(now.timestamp()), timezone.utc)
        self.assertEqual(target, now.replace(minute=30, second=20))
        latest = Bar(target.replace(second=0) - timedelta(minutes=5),
                     4010, 4012, 4008, 4009, 5)
        self.assertEqual(require_fresh([latest], target, 120), 20)
        # A provider that still returns the older candle remains rejected.
        with self.assertRaises(DataError):
            require_fresh([last], target, 120)

    def test_processing_time_does_not_accumulate_drift(self):
        target = 20
        for duration in (6, 15, 45, 61, 7, 20):
            following = next_official_cycle(target + duration)
            self.assertEqual(following - target, 900)
            self.assertEqual(following % 300, 20)
            target = following

    def test_startup_and_stale_retry_use_next_five_minute_boundary(self):
        for epoch in (1, 19, 20, 120, 174, 299, 301):
            target = next_official_cycle(epoch, 300)
            self.assertGreater(target, epoch)
            self.assertLessEqual(target - epoch, 300)
            self.assertEqual(target % 300, 20)

    def test_delayed_loop_skips_missed_boundaries_and_custom_intervals_align(self):
        self.assertEqual(next_official_cycle(1821), 2720)
        for interval in (60, 300, 600, 900, 1000):
            self.assertEqual(next_official_cycle(1234, interval) % 300, 20)


if __name__ == "__main__":
    unittest.main()
