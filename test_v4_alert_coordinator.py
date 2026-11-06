import unittest
from datetime import datetime, timedelta, timezone
from v4_alert_coordinator import run_alert_cycle


class MemoryStore:
    def __init__(self):
        self.data = {}
    def get(self, key):
        return self.data.get(key)
    def set(self, key, value):
        self.data[key] = value


class TelegramFake:
    def __init__(self):
        self.sent = []
    def send(self, message):
        self.sent.append(message)
        return True


class CoordinatorTests(unittest.TestCase):
    def test_close_and_news_once_across_cycles(self):
        now = datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)
        sessions = [(now - timedelta(hours=2), now + timedelta(minutes=30))]
        news = [dict(id="us-news", release_at=now + timedelta(minutes=20),
                     importance="high", calendar_verified=True)]
        store, notifier = MemoryStore(), TelegramFake()
        kwargs = dict(store=store, notifier=notifier, broker_sessions=sessions,
                      quote_at=now, verified_news_events=news)
        self.assertEqual(len(run_alert_cycle(now, **kwargs)), 2)
        self.assertEqual(run_alert_cycle(now, **kwargs), [])
        self.assertEqual(len(notifier.sent), 2)

    def test_missing_data_fails_closed(self):
        now = datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)
        store, notifier = MemoryStore(), TelegramFake()
        self.assertEqual(run_alert_cycle(now, store=store, notifier=notifier,
                         broker_sessions=[], quote_at=None), [])

if __name__ == "__main__":
    unittest.main()
