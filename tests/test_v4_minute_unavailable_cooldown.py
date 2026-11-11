import unittest
from v4_minute_safety import should_notify_unavailable


class MinuteUnavailableCooldownTests(unittest.TestCase):
    def test_first_failure_notifies(self):
        self.assertTrue(should_notify_unavailable(None, 1794380137))

    def test_recovery_then_failure_two_minutes_later_is_suppressed(self):
        self.assertFalse(should_notify_unavailable(1794380137, 1794380257))

    def test_repeated_failure_after_fifteen_minutes_notifies(self):
        self.assertTrue(should_notify_unavailable(1794380137, 1794381037))

    def test_prior_outage_never_disables_new_safety_warning(self):
        self.assertFalse(should_notify_unavailable(1794380137, 1794380437))


if __name__ == '__main__':
    unittest.main()
