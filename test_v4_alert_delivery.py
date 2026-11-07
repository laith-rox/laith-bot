import unittest
from v4_alert_delivery import deliver_once


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
        self.messages = []
    def send(self, message):
        self.messages.append(message)
        return self.result


class DeliveryTests(unittest.TestCase):
    def test_deliver_once(self):
        store, notifier = Store(), Notifier()
        notice = dict(key="news:1", message="Alert")
        self.assertTrue(deliver_once(store, notifier, notice))
        self.assertFalse(deliver_once(store, notifier, notice))
        self.assertEqual(notifier.messages, ["Alert"])

    def test_failed_delivery_retryable(self):
        store, notifier = Store(), Notifier(result=False)
        notice = dict(key="news:1", message="Alert")
        self.assertFalse(deliver_once(store, notifier, notice))
        notifier.result = True
        self.assertTrue(deliver_once(store, notifier, notice))

    def test_unconfirmed_delivery_does_not_mark_sent(self):
        store, notifier = Store(), Notifier(result=None)
        notice = dict(key="news:2", message="Alert")
        self.assertFalse(deliver_once(store, notifier, notice))
        self.assertIsNone(store.get("v4_alert_sent:news:2"))
        notifier.result = True
        self.assertTrue(deliver_once(store, notifier, notice))

    def test_invalid_notice(self):
        self.assertFalse(deliver_once(Store(), Notifier(), {}))


if __name__ == "__main__":
    unittest.main()


class TransportFailureTests(unittest.TestCase):
    def test_transport_failures_do_not_mark_alert_sent(self):
        for failure in (TimeoutError, ConnectionError, OSError):
            with self.subTest(failure=failure):
                store = Store()
                class FlakyNotifier:
                    def __init__(self):
                        self.calls = 0
                    def send(self, message):
                        self.calls += 1
                        if self.calls == 1:
                            raise failure("telegram transport unavailable")
                        return True
                notifier = FlakyNotifier()
                notice = {"key": "emergency:42", "message": "V4 emergency"}
                self.assertFalse(deliver_once(store, notifier, notice))
                self.assertIsNone(store.get("v4_alert_sent:emergency:42"))
                self.assertTrue(deliver_once(store, notifier, notice))
                self.assertFalse(deliver_once(store, notifier, notice))
                self.assertEqual(notifier.calls, 2)
