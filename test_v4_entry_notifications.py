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
