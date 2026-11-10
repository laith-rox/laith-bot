"""End-to-end V4 safety contract with synthetic inputs; no real Telegram or broker."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from v4_verified_calendar import verified_sessions, verified_news
from v4_broker_entry_guard import broker_entry_eligibility
from v4_entry_notifications import plan_entry_notification, publish_entry_notification
from v4_alert_coordinator import run_alert_cycle


class Store:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


class TelegramStub:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


class V4ManualSignalIntegrationTests(unittest.TestCase):
    def test_verified_calendar_news_and_stale_quote_block_then_dedupe(self):
        now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        session_json = json.dumps({"verified": True, "sessions": [{
            "open": "2026-11-09T10:00:00Z",
            "close": "2026-11-09T18:00:00Z"
        }]})
        news_json = json.dumps({"verified": True, "events": [{
            "id": "cpi", "title": "US CPI", "importance": "high",
            "release_at": "2026-11-09T12:20:00Z"
        }]})
        sessions = verified_sessions(session_json)
        news = verified_news(news_json)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(news), 1)

        store, telegram = Store(), TelegramStub()
        due = run_alert_cycle(now, store=store, notifier=telegram,
                              broker_sessions=sessions, quote_at=now,
                              verified_news_events=news)
        self.assertEqual(len(due), 1)
        self.assertEqual(run_alert_cycle(now, store=store, notifier=telegram,
                         broker_sessions=sessions, quote_at=now,
                         verified_news_events=news), [])
        self.assertEqual(len(telegram.messages), 1)

        candidate = {"state": "READY", "side": "BUY", "horizon": "SCALP",
                     "entry": 4000, "stop": 3995, "target": 4010}
        old_quote = now - timedelta(minutes=3)
        allowed, _ = broker_entry_eligibility(now, sessions, old_quote,
                                              bar_end_at=now - timedelta(minutes=5))
        self.assertFalse(allowed)
        self.assertIsNone(plan_entry_notification(
            store, candidate, session_id="verified-20261109",
            market_state="OPEN", quote_verified=allowed, news_safe=True))

        allowed, _ = broker_entry_eligibility(
            now, sessions, now - timedelta(seconds=5),
            bar_end_at=now - timedelta(minutes=5))
        self.assertTrue(allowed)
        self.assertIsNone(plan_entry_notification(
            store, candidate, session_id="verified-20261109",
            market_state="OPEN", quote_verified=allowed, news_safe=False))
        planned = plan_entry_notification(
            store, candidate, session_id="verified-20261109",
            market_state="OPEN", quote_verified=allowed, news_safe=True)
        self.assertIsNotNone(planned)
        self.assertTrue(publish_entry_notification(store, telegram, planned))
        self.assertFalse(publish_entry_notification(store, telegram, planned))
        self.assertEqual(len(telegram.messages), 2)

    def test_unverified_broker_calendar_blocks_entry(self):
        now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        sessions = verified_sessions(json.dumps({"verified": False, "sessions": [{
            "open": "2026-11-09T10:00:00Z",
            "close": "2026-11-09T18:00:00Z"
        }]}))
        self.assertFalse(broker_entry_eligibility(now, sessions, now)[0])


if __name__ == "__main__":
    unittest.main()
