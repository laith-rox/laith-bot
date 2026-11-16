import unittest
from datetime import datetime, timezone
from v4_hourly_status import should_send_hourly_status, hourly_status_message


class HourlyStatusTests(unittest.TestCase):
    def test_waits_full_hour(self):
        self.assertFalse(should_send_hourly_status(3599, 0, None, True))
        self.assertTrue(should_send_hourly_status(3600, 0, None, True))

    def test_market_closed_or_unknown_entry_never_sends(self):
        self.assertFalse(should_send_hourly_status(7200, 0, None, False))
        self.assertFalse(should_send_hourly_status(7200, None, None, True))

    def test_deduplicates_for_an_hour(self):
        self.assertFalse(should_send_hourly_status(7100, 0, 3600, True))
        self.assertTrue(should_send_hourly_status(7200, 0, 3600, True))

    def test_new_entry_resets_notice(self):
        self.assertFalse(should_send_hourly_status(7300, 7200, 3600, True))

    def test_message_uses_observed_volatility_only(self):
        self.assertIn("تقلبات طبيعية", hourly_status_message("NORMAL", "منطقة انتظار"))
        self.assertNotIn("تقلبات مرتفعة", hourly_status_message(None, None))
        self.assertIn("تقلبات شديدة", hourly_status_message("EXTREME", "تقلبات قوية"))


if __name__ == "__main__":
    unittest.main()
