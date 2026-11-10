import unittest
from datetime import datetime, timedelta, timezone
from v4_broker_entry_guard import broker_entry_eligibility

UTC = timezone.utc

class BrokerEntryEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.opened = datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
        self.closed = self.opened + timedelta(hours=22)
        self.now = self.opened + timedelta(minutes=20)
        self.sessions = ((self.opened, self.closed),)

    def test_fresh_post_open_quote_and_closed_bar(self):
        allowed, reason = broker_entry_eligibility(self.now, self.sessions,
            self.now - timedelta(seconds=10), bar_end_at=self.opened + timedelta(minutes=15))
        self.assertTrue(allowed, reason)

    def test_reject_old_session_quote(self):
        allowed, _ = broker_entry_eligibility(self.now, self.sessions,
            self.opened - timedelta(seconds=1))
        self.assertFalse(allowed)

    def test_reject_old_indicator_candle_even_with_fresh_quote(self):
        allowed, reason = broker_entry_eligibility(self.now, self.sessions,
            self.now - timedelta(seconds=10), bar_end_at=self.opened - timedelta(minutes=5))
        self.assertFalse(allowed)
        self.assertEqual(reason, "indicator_bar_from_previous_session")

    def test_pre_close_block_and_missing_calendar(self):
        allowed, reason = broker_entry_eligibility(self.closed - timedelta(minutes=10),
            self.sessions, self.closed - timedelta(minutes=10, seconds=5))
        self.assertFalse(allowed)
        self.assertEqual(reason, "last_30_minutes")
        self.assertFalse(broker_entry_eligibility(self.now, (), self.now)[0])

    def test_bar_newer_than_quote_is_blocked(self):
        quote = self.now - timedelta(seconds=20)
        bar_end = self.now - timedelta(seconds=5)
        allowed, reason = broker_entry_eligibility(self.now, self.sessions,
            quote, bar_end_at=bar_end)
        self.assertFalse(allowed)
        self.assertEqual(reason, "indicator_bar_newer_than_quote")

    def test_future_indicator_bar_blocked(self):
        allowed, _ = broker_entry_eligibility(self.now, self.sessions, self.now,
            bar_end_at=self.now + timedelta(minutes=5))
        self.assertFalse(allowed)

if __name__ == '__main__': unittest.main()
