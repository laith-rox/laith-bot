import unittest
from datetime import datetime, timezone, timedelta
from v4_pending_entry import pending_entry_retry_allowed

class PendingEntryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
        self.pending = {"candidate": {"side": "BUY"}, "session_id": "2026-11-09", "message": "manual entry", "observed_at": self.now.timestamp() - 30}

    def allowed(self, pending=None, now=None, closed=False, news=True):
        return pending_entry_retry_allowed(self.pending if pending is None else pending, self.now if now is None else now, market_closed=closed, news_allowed=news)

    def test_fresh_open_news_clear(self):
        self.assertTrue(self.allowed())

    def test_closed(self):
        self.assertFalse(self.allowed(closed=True))

    def test_news_blackout(self):
        self.assertFalse(self.allowed(news=False))

    def test_expired(self):
        self.assertFalse(self.allowed({**self.pending, "observed_at": self.now.timestamp() - 91}))

    def test_future(self):
        self.assertFalse(self.allowed({**self.pending, "observed_at": self.now.timestamp() + 11}))

    def test_session_changed(self):
        self.assertFalse(self.allowed({**self.pending, "session_id": "2026-11-08"}))

    def test_naive_clock_fails_closed(self):
        self.assertFalse(self.allowed(now=self.now.replace(tzinfo=None)))

    def test_malformed(self):
        self.assertFalse(self.allowed({**self.pending, "candidate": None}))
        self.assertFalse(self.allowed({**self.pending, "message": ""}))
        self.assertFalse(self.allowed({**self.pending, "observed_at": "nan"}))

if __name__ == "__main__":
    unittest.main()
