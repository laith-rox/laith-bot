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

    def test_invalid_notice(self):
        self.assertFalse(deliver_once(Store(), Notifier(), {}))


if __name__ == "__main__":
    unittest.main()
