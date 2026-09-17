from datetime import datetime, timezone
import unittest

from v4_emergency import emergency_message, reversal_snapshot, scan_emergencies

UTC = timezone.utc


class MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class Notifier:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


class V4EmergencyTests(unittest.TestCase):
    def test_opposite_condition_dominance_triggers_warning(self):
        decision = {
            "side": "WAIT",
            "price": 4300.0,
            "checks": {
                "BUY": [True, True, False, False, False, False, False],
                "SELL": [True, True, True, True, True, True, False],
            },
            "v4": {"correction": {}, "breakout_state": "LEVEL_INTACT"},
        }
        trade = {"id": "q1", "kind": "QUICK", "side": "BUY", "entry": 4302.0, "stop": 4297.0}
        snap = reversal_snapshot(decision, trade)
        self.assertIsNotNone(snap)
        self.assertEqual(snap["own_score"], 2)
        self.assertEqual(snap["opposite_score"], 6)
        self.assertIn("شروط الاتجاه المعاكس أصبحت أقوى", " ".join(snap["reasons"]))

    def test_strong_adverse_correction_is_high_emergency(self):
        decision = {
            "side": "WAIT",
            "price": 4300.0,
            "checks": {"BUY": [True] * 5 + [False, False], "SELL": [True] * 3 + [False] * 4},
            "v4": {
                "breakout_state": "LEVEL_INTACT",
                "correction": {
                    "triggered": True,
                    "strength": "STRONG",
                    "direction": "DOWN",
                    "target1": 4292.0,
                    "target2": 4287.0,
                },
            },
        }
        trade = {"id": "q2", "kind": "QUICK", "side": "BUY", "entry": 4304.0, "stop": 4299.0}
        snap = reversal_snapshot(decision, trade)
        self.assertEqual(snap["severity"], "مرتفعة")
        message = emergency_message(snap)
        self.assertIn("🚨", message)
        self.assertIn("4292.00", message)
        self.assertIn("لا يغلق الصفقة", message)

    def test_scan_deduplicates_same_warning(self):
        store = MemoryStore()
        notifier = Notifier()
        now = datetime(2026, 9, 17, 5, 30, tzinfo=UTC)
        decision = {
            "side": "SELL",
            "price": 4300.0,
            "checks": {"BUY": [True] * 2 + [False] * 5, "SELL": [True] * 6 + [False]},
            "v4": {"correction": {}, "breakout_state": "LEVEL_INTACT"},
        }
        trade = {
            "id": "q3",
            "kind": "QUICK",
            "side": "BUY",
            "status": "active",
            "announced": now.timestamp() - 300,
            "entry": 4301.0,
            "stop": 4296.0,
        }
        first = scan_emergencies(store, notifier, decision, None, [trade], now)
        second = scan_emergencies(store, notifier, decision, None, [trade], now)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(notifier.messages), 1)

    def test_no_warning_for_new_quick_on_same_observation(self):
        store = MemoryStore()
        notifier = Notifier()
        now = datetime(2026, 9, 17, 5, 30, tzinfo=UTC)
        decision = {
            "side": "SELL",
            "price": 4300.0,
            "checks": {"BUY": [True] * 2 + [False] * 5, "SELL": [True] * 6 + [False]},
            "v4": {"correction": {}, "breakout_state": "LEVEL_INTACT"},
        }
        trade = {
            "id": "q4",
            "kind": "QUICK",
            "side": "BUY",
            "status": "active",
            "announced": now.timestamp(),
        }
        alerts = scan_emergencies(store, notifier, decision, None, [trade], now)
        self.assertEqual(alerts, [])
        self.assertEqual(notifier.messages, [])


if __name__ == "__main__":
    unittest.main()
