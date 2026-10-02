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
        self.assertIsNone(snap)

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

    def test_no_reversal_when_original_side_is_stronger(self):
        decision = {
            "side": "WAIT",
            "price": 4300.0,
            "checks": {"BUY": [True] * 5 + [False, False], "SELL": [True] + [False] * 6},
            "v4": {
                "breakout_state": "LEVEL_INTACT",
                "correction": {"triggered": True, "strength": "STRONG", "direction": "DOWN"},
            },
        }
        trade = {"id": "q-strong", "kind": "QUICK", "side": "BUY", "entry": 4300.0, "stop": 4295.0}
        self.assertIsNone(reversal_snapshot(decision, trade))

    def test_score_fluctuation_does_not_repeat_same_emergency(self):
        store = MemoryStore()
        notifier = Notifier()
        now = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
        trade = {
            "id": "q-dedupe", "kind": "QUICK", "side": "BUY", "status": "active",
            "announced": now.timestamp() - 600, "entry": 4300.0, "stop": 4295.0,
        }
        first_decision = {
            "side": "WAIT", "price": 4298.0,
            "checks": {"BUY": [True, True] + [False] * 5, "SELL": [True] * 6 + [False]},
            "v4": {"correction": {}, "breakout_state": "LEVEL_INTACT"},
        }
        second_decision = {
            "side": "WAIT", "price": 4297.0,
            "checks": {"BUY": [True] * 3 + [False] * 4, "SELL": [True] * 6 + [False]},
            "v4": {"correction": {}, "breakout_state": "LEVEL_INTACT"},
        }
        self.assertEqual(len(scan_emergencies(store, notifier, first_decision, None, [trade], now)), 1)
        self.assertEqual(len(scan_emergencies(store, notifier, second_decision, None, [trade], now)), 0)
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
