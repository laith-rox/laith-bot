import unittest
from datetime import datetime, timedelta, timezone
from v4_market_guard import market_guard, close_alert_key, valid_post_open_quote

UTC = timezone.utc

class MarketGuardTests(unittest.TestCase):
    def setUp(self):
        self.opened = datetime(2026, 11, 6, 12, tzinfo=UTC)
        self.closed = self.opened + timedelta(hours=5)
        self.windows = [(self.opened, self.closed)]

    def check(self, now, quote=None):
        return market_guard(now, self.windows, last_quote_at=quote)[0]

    def test_open(self):
        t = self.opened + timedelta(hours=1)
        self.assertEqual(self.check(t, t), "OPEN")

    def test_thirty_minute_warning(self):
        t = self.closed - timedelta(minutes=30)
        self.assertEqual(self.check(t, t), "PRE_CLOSE")

    def test_close_blocks_entries(self):
        self.assertEqual(self.check(self.closed, self.closed), "CLOSED")

    def test_missing_calendar_fails_closed(self):
        self.assertEqual(market_guard(self.opened, [], last_quote_at=self.opened)[0], "CLOSED")

    def test_stale_quote_waits(self):
        t = self.opened + timedelta(hours=1)
        self.assertEqual(self.check(t, self.opened), "WAIT")

    def test_old_quote_rejected_on_reopen(self):
        self.assertFalse(valid_post_open_quote(self.opened - timedelta(seconds=1),
                                               self.opened, self.opened))

    def test_warning_key_is_deterministic(self):
        self.assertEqual(close_alert_key(self.closed), close_alert_key(self.closed))
        self.assertNotEqual(close_alert_key(self.closed), close_alert_key(self.closed, weekly=True))

if __name__ == "__main__":
    unittest.main()
