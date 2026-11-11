import unittest
from v4_minute_safety import should_alert_unavailable, should_alert_recovery


class MinuteOutageCooldownTests(unittest.TestCase):
    def test_first_outage_alerts(self):
        self.assertTrue(should_alert_unavailable(None, 1000))

    def test_repeated_outage_within_fifteen_minutes_is_silent(self):
        self.assertFalse(should_alert_unavailable(1000, 1120))
        self.assertFalse(should_alert_unavailable(1000, 1899))

    def test_reminder_after_fifteen_minutes(self):
        self.assertTrue(should_alert_unavailable(1000, 1900))

    def test_recovery_only_after_outage(self):
        self.assertTrue(should_alert_recovery({'ok': False}))
        self.assertFalse(should_alert_recovery({'ok': True}))
        self.assertFalse(should_alert_recovery({}))


if __name__ == '__main__':
    unittest.main()
