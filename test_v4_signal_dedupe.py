import unittest
from v4_signal_dedupe import signal_identity, should_publish_signal, mark_signal_published


class Store:
    def __init__(self):
        self.data = {}
    def get(self, key):
        return self.data.get(key)
    def set(self, key, value):
        self.data[key] = value


class SignalDedupeTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.signal = dict(state="READY", side="BUY", horizon="SCALP",
                           entry=3000, stop=2998, target=3004)

    def test_ready_once_per_session(self):
        self.assertTrue(should_publish_signal(self.store, self.signal, session_id="s1"))
        mark_signal_published(self.store, self.signal, session_id="s1")
        self.assertFalse(should_publish_signal(self.store, self.signal, session_id="s1"))
        self.assertTrue(should_publish_signal(self.store, self.signal, session_id="s2"))

    def test_wait_never_publishes(self):
        self.signal["state"] = "WATCH"
        self.assertFalse(should_publish_signal(self.store, self.signal, session_id="s1"))

    def test_missing_session_never_publishes(self):
        self.assertFalse(should_publish_signal(self.store, self.signal, session_id=None))

    def test_bad_geometry_rejected(self):
        self.signal["stop"] = 3002
        self.assertIsNone(signal_identity(self.signal))

    def test_nan_rejected(self):
        self.signal["entry"] = float("nan")
        self.assertIsNone(signal_identity(self.signal))

if __name__ == "__main__":
    unittest.main()
