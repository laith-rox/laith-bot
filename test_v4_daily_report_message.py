import unittest
from datetime import date
from v4_daily_report_message import daily_report_message


class DailyReportMessageTests(unittest.TestCase):
    def test_compact_counts(self):
        text = daily_report_message(date(2026, 11, 13), {"total": {"wins": 4, "losses": 2}})
        self.assertIn("ناجحة: 4", text)
        self.assertIn("فاشلة: 2", text)
        self.assertIn("13/11/2026", text)

    def test_zero_day(self):
        text = daily_report_message(date(2026, 11, 13), {"total": {"wins": 0, "losses": 0}})
        self.assertIn("ناجحة: 0", text)
        self.assertIn("فاشلة: 0", text)


if __name__ == "__main__":
    unittest.main()
