import unittest
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from v4_daily_report import daily_trade_counts, should_send_report


class DailyReportTests(unittest.TestCase):
    def test_counts_separate_lanes_and_excludes_open(self):
        t = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc).timestamp()
        o = [{"status": "closed", "closed": t, "r": 1.5}, {"status": "active", "r": -1}]
        q = [{"status": "closed", "closed": t, "r": -1}, {"status": "closed", "closed": t, "r": 0}]
        result = daily_trade_counts(o, q, date(2026, 11, 13))
        self.assertEqual(result["total"], {"wins": 1, "losses": 1, "unresolved": 1, "win_rate": 50.0})

    def test_local_day_boundary(self):
        t = datetime(2026, 11, 13, 22, 30, tzinfo=timezone.utc).timestamp()
        self.assertEqual(daily_trade_counts([{"status": "closed", "closed": t, "r": 1}], [], date(2026, 11, 13))["total"]["wins"], 0)
        self.assertEqual(daily_trade_counts([{"status": "closed", "closed": t, "r": 1}], [], date(2026, 11, 14))["total"]["wins"], 1)

    def test_missing_result_is_not_loss(self):
        t = datetime(2026, 11, 13, 20, tzinfo=timezone.utc).timestamp()
        result = daily_trade_counts([{"status": "closed", "closed": t}], [], date(2026, 11, 13))
        self.assertEqual(result["total"]["unresolved"], 1)
        self.assertIsNone(result["total"]["win_rate"])

    def test_schedule_and_duplicate(self):
        tz = ZoneInfo("Asia/Hebron")
        before = datetime(2026, 11, 13, 23, 29, tzinfo=tz)
        after = datetime(2026, 11, 13, 23, 30, tzinfo=tz)
        self.assertFalse(should_send_report(before, None))
        self.assertTrue(should_send_report(after, None))
        self.assertFalse(should_send_report(after, "2026-11-13"))


if __name__ == "__main__":
    unittest.main()
