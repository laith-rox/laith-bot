import unittest
from datetime import datetime, timezone
from v4_daily_report import plan_daily_decision_report

UTC = timezone.utc

class DailyReportTests(unittest.TestCase):
    def test_previous_local_day_only(self):
        now = datetime(2026, 11, 7, 7, 0, tzinfo=UTC)
        events = [
            {"observed_at": "2026-11-06T21:30:00+00:00", "state": "READY", "reason": "confirmed"},
            {"observed_at": "2026-11-06T19:30:00+00:00", "state": "REJECTED", "reason": "stale"},
            {"observed_at": "2026-11-07T04:00:00+00:00", "state": "WAIT", "reason": "waiting"},
        ]
        result = plan_daily_decision_report(now, events)
        self.assertEqual(result["key"], "v4_daily_decisions:2026-11-06")
        self.assertIn("جاهزة: 1", result["message"])
        self.assertIn("مرفوضة: 1", result["message"])
        self.assertNotIn("نسبة نجاح: 100", result["message"])

    def test_quiet_before_morning_and_empty(self):
        events = [{"observed_at": "2026-11-06T19:30:00Z", "state": "READY", "reason": "ok"}]
        self.assertIsNone(plan_daily_decision_report(datetime(2026,11,7,3,tzinfo=UTC),events))
        self.assertIsNone(plan_daily_decision_report(datetime(2026,11,7,8,tzinfo=UTC),[]))

    def test_reject_future_and_bad_rows(self):
        now = datetime(2026,11,7,8,tzinfo=UTC)
        events = [{"observed_at":"2026-11-08T10:00:00Z", "state":"READY", "reason":"future"},
                  {"observed_at":"not-a-date", "state":"READY", "reason":"bad"}]
        self.assertIsNone(plan_daily_decision_report(now,events))
        with self.assertRaises(ValueError):
            plan_daily_decision_report(datetime(2026,11,7,8),events)

if __name__ == '__main__': unittest.main()
