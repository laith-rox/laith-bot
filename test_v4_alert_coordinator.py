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


class CoordinatorTransportRecoveryTests(unittest.TestCase):
    def test_failed_close_alert_retries_without_resending_successful_news(self):
        now = datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)
        sessions = [(now - timedelta(hours=2), now + timedelta(minutes=30))]
        news = [dict(id="us-news", release_at=now + timedelta(minutes=20),
                     importance="high", calendar_verified=True)]
        class FlakyTelegram:
            def __init__(self):
                self.calls = 0
                self.sent = []
            def send(self, message):
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutError("Telegram timeout")
                self.sent.append(message)
                return True
        store, notifier = MemoryStore(), FlakyTelegram()
        kwargs = dict(store=store, notifier=notifier, broker_sessions=sessions,
                      quote_at=now, verified_news_events=news)
        first = run_alert_cycle(now, **kwargs)
        self.assertEqual(len(first), 1)
        second = run_alert_cycle(now, **kwargs)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(run_alert_cycle(now, **kwargs), [])
        self.assertEqual(notifier.calls, 3)
        self.assertEqual(len(notifier.sent), 2)


class VerifiedCalendarCoordinatorIntegrationTests(unittest.TestCase):
    def test_unverified_calendar_never_generates_news_alerts(self):
        import json
        from v4_verified_calendar import verified_news
        now = datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)
        event = {"id": "CPI", "title": "CPI", "release_at": "2026-11-06T14:00:00Z", "importance": "high"}
        store, notifier = MemoryStore(), TelegramFake()
        for verified in (False, True):
            raw = json.dumps({"verified": verified, "events": [event]})
            delivered = run_alert_cycle(now, store=store, notifier=notifier,
                broker_sessions=(), quote_at=None, verified_news_events=verified_news(raw))
            if verified:
                self.assertEqual(len(delivered), 1)
            else:
                self.assertEqual(delivered, [])
        self.assertEqual(len(notifier.sent), 1)
        self.assertEqual(run_alert_cycle(now, store=store, notifier=notifier,
            broker_sessions=(), quote_at=None,
            verified_news_events=verified_news(json.dumps({"verified": True, "events": [event]}))), [])

    def test_duplicate_external_event_ids_fail_closed_before_delivery(self):
        import json
        from v4_verified_calendar import verified_news
        now = datetime(2026, 11, 6, 13, 40, tzinfo=timezone.utc)
        events = [
            {"id": "CPI", "title": "CPI", "release_at": "2026-11-06T14:00:00Z", "importance": "high"},
            {"id": " cpi ", "title": "Other", "release_at": "2026-11-06T14:05:00Z", "importance": "high"},
        ]
        store, notifier = MemoryStore(), TelegramFake()
        delivered = run_alert_cycle(now, store=store, notifier=notifier,
            broker_sessions=(), quote_at=None,
            verified_news_events=verified_news(json.dumps({"verified": True, "events": events})))
        self.assertEqual(delivered, [])
        self.assertEqual(notifier.sent, [])
