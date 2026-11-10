import unittest
from v4_entry_notifications import plan_entry_notification, publish_entry_notification


class Store:
    def __init__(self):
        self.data = {}
    def get(self, key):
        return self.data.get(key)
    def set(self, key, value):
        self.data[key] = value


class Notifier:
    def __init__(self, result=True):
        self.result = result
        self.sent = []
    def send(self, message):
        self.sent.append(message)
        return self.result


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.signal = dict(state="READY", side="BUY", horizon="SCALP",
                           entry=3000, stop=2998, target=3004)
        self.args = dict(session_id="session1", market_state="OPEN",
                         quote_verified=True, news_safe=True)

    def plan(self, **changes):
        return plan_entry_notification(self.store, self.signal,
                                       **dict(self.args, **changes))

    def test_valid_manual_entry(self):
        planned = self.plan()
        self.assertIn("دخول يدوي", planned["message"])
        notifier = Notifier()
        self.assertTrue(publish_entry_notification(self.store, notifier, planned))
        self.assertIsNone(self.plan())

    def test_original_candidate_mutation_cannot_change_planned_levels(self):
        planned = self.plan()
        self.signal["entry"] = 3100
        self.signal["stop"] = 3090
        self.assertEqual(planned["candidate"]["entry"], 3000)
        self.assertTrue(publish_entry_notification(self.store, Notifier(), planned))

    def test_mutated_planned_candidate_never_sends_mismatched_message(self):
        planned = self.plan()
        planned["candidate"]["entry"] = 3100
        notifier = Notifier()
        self.assertFalse(publish_entry_notification(self.store, notifier, planned))
        self.assertEqual(notifier.sent, [])

    def test_untrusted_horizon_is_html_escaped(self):
        self.signal["horizon"] = '<b>FAKE</b>&"'
        planned = self.plan()
        self.assertIsNotNone(planned)
        self.assertIn("&lt;b&gt;FAKE&lt;/b&gt;&amp;&quot;", planned["message"])
        self.assertNotIn("<b>FAKE</b>", planned["message"])

    def test_market_closed(self):
        self.assertIsNone(self.plan(market_state="CLOSED"))

    def test_market_preclose(self):
        self.assertIsNone(self.plan(market_state="PRE_CLOSE"))

    def test_unverified_quote(self):
        self.assertIsNone(self.plan(quote_verified=False))

    def test_news_risk(self):
        self.assertIsNone(self.plan(news_safe=False))

    def test_transport_timeout_keeps_signal_retryable(self):
        planned = self.plan()
        class TimedOut:
            def send(self, message):
                raise TimeoutError("network timeout")
        self.assertFalse(publish_entry_notification(self.store, TimedOut(), planned))
        self.assertIsNotNone(self.plan())
        notifier = Notifier(True)
        self.assertTrue(publish_entry_notification(self.store, notifier, planned))
        self.assertFalse(publish_entry_notification(self.store, notifier, planned))
        self.assertEqual(len(notifier.sent), 1)

    def test_connection_error_keeps_signal_retryable(self):
        planned = self.plan()
        class Disconnected:
            def send(self, message):
                raise ConnectionError("connection reset")
        self.assertFalse(publish_entry_notification(self.store, Disconnected(), planned))
        self.assertIsNotNone(self.plan())

    def test_send_failure_does_not_mark(self):
        planned = self.plan()
        self.assertFalse(publish_entry_notification(self.store, Notifier(False), planned))
        self.assertIsNotNone(self.plan())

if __name__ == "__main__":
    unittest.main()


class BrokerGuardToTelegramIntegrationTests(unittest.TestCase):
    def test_stale_quote_blocks_manual_telegram_entry(self):
        from datetime import datetime, timedelta, timezone
        from v4_broker_entry_guard import broker_entry_eligibility
        now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        sessions = ((now - timedelta(hours=1), now + timedelta(hours=1)),)
        store, notifier = Store(), Notifier()
        signal = dict(state="READY", side="BUY", horizon="SCALP",
                      entry=4000, stop=3995, target=4010)
        stale = now - timedelta(minutes=3)
        allowed, reason = broker_entry_eligibility(now, sessions, stale,
            bar_end_at=now - timedelta(minutes=5))
        self.assertFalse(allowed, reason)
        planned = plan_entry_notification(store, signal, session_id="verified-session",
            market_state="OPEN" if allowed else "WAIT", quote_verified=allowed,
            news_safe=True)
        self.assertIsNone(planned)
        self.assertFalse(publish_entry_notification(store, notifier, planned))
        self.assertEqual(notifier.sent, [])

    def test_fresh_quote_allows_one_manual_telegram_entry(self):
        from datetime import datetime, timedelta, timezone
        from v4_broker_entry_guard import broker_entry_eligibility
        now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        sessions = ((now - timedelta(hours=1), now + timedelta(hours=1)),)
        allowed, reason = broker_entry_eligibility(now, sessions,
            now - timedelta(seconds=5), bar_end_at=now - timedelta(minutes=5))
        self.assertTrue(allowed, reason)
        store, notifier = Store(), Notifier()
        signal = dict(state="READY", side="BUY", horizon="SCALP",
                      entry=4000, stop=3995, target=4010)
        planned = plan_entry_notification(store, signal, session_id="verified-session",
            market_state="OPEN", quote_verified=allowed, news_safe=True)
        self.assertIsNotNone(planned)
        self.assertTrue(publish_entry_notification(store, notifier, planned))
        self.assertFalse(publish_entry_notification(store, notifier, planned))
        self.assertEqual(len(notifier.sent), 1)


class BrokerPrecloseToTelegramIntegrationTests(unittest.TestCase):
    def test_preclose_blocks_manual_entry_even_with_fresh_quote(self):
        from datetime import datetime, timedelta, timezone
        from v4_broker_entry_guard import broker_entry_eligibility
        now = datetime(2026, 11, 9, 21, 45, tzinfo=timezone.utc)
        sessions = ((now - timedelta(hours=2), now + timedelta(minutes=15)),)
        allowed, reason = broker_entry_eligibility(now, sessions,
            now - timedelta(seconds=5), bar_end_at=now - timedelta(minutes=5))
        self.assertFalse(allowed)
        self.assertEqual(reason, "last_30_minutes")
        store, notifier = Store(), Notifier()
        candidate = dict(state="READY", side="BUY", entry=4000, stop=3995, target=4010)
        planned = plan_entry_notification(store, candidate, session_id="verified-session",
            market_state="PRE_CLOSE", quote_verified=allowed, news_safe=True)
        self.assertIsNone(planned)
        self.assertFalse(publish_entry_notification(store, notifier, planned))
        self.assertEqual(notifier.sent, [])
