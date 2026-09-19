from datetime import datetime, timezone
import unittest

from v4_weekend_education import (
    build_weekend_education_message,
    maybe_send_weekend_education,
    weekend_education_window,
)

UTC = timezone.utc


class FakeStore:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class FakePaper:
    def __init__(self, winners=None):
        self.winners = list(winners or [])

    def _paper_rows(self):
        return list(self.winners)

    def _quick_rows(self):
        return []


class WeekendEducationTests(unittest.TestCase):
    def test_window_starts_at_local_saturday_midnight(self):
        before_local_saturday = datetime(2026, 9, 18, 20, 59, tzinfo=UTC)  # 23:59 Hebron
        local_saturday = datetime(2026, 9, 18, 21, 0, tzinfo=UTC)          # 00:00 Hebron
        self.assertFalse(weekend_education_window(before_local_saturday))
        self.assertTrue(weekend_education_window(local_saturday))

    def test_window_stops_at_sunday_new_york_reopen(self):
        before_open = datetime(2026, 9, 20, 21, 59, tzinfo=UTC)  # 17:59 New York / Mon 00:59 Hebron
        at_open = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)       # 18:00 New York / Mon 01:00 Hebron
        self.assertTrue(weekend_education_window(before_open))
        self.assertFalse(weekend_education_window(at_open))

    def test_sends_only_once_per_hour(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        now = datetime(2026, 9, 19, 16, 5, tzinfo=UTC)
        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, now))
        self.assertFalse(maybe_send_weekend_education(store, notifier, paper, now.replace(minute=55)))
        self.assertEqual(len(notifier.messages), 1)
        self.assertIn("صفقة تعليمية", notifier.messages[0])
        self.assertIn("ليست إشارة دخول", notifier.messages[0])

    def test_next_hour_sends_again(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        first = datetime(2026, 9, 19, 16, 5, tzinfo=UTC)
        second = datetime(2026, 9, 19, 17, 5, tzinfo=UTC)
        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, first))
        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, second))
        self.assertEqual(len(notifier.messages), 2)

    def test_profitable_saved_trade_is_used_as_real_lesson(self):
        winner = {
            "id": "q-win",
            "status": "closed",
            "side": "BUY",
            "entry": 4300,
            "stop": 4295,
            "target": 4310,
            "r": 1.8,
            "score": 6,
            "conditions": [{"name": "اتجاه 15د", "ok": True}],
        }
        paper = FakePaper([winner])
        # Pick a four-hour rotation slot reserved for a saved V4 winner.
        now = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
        while int(now.timestamp() // 3600) % 4 != 0:
            now = now.replace(hour=now.hour + 1)
        message = build_weekend_education_message(paper, now)
        self.assertIn("من سجل Laith V4", message)
        self.assertIn("4300.00", message)
        self.assertIn("+1.80R", message)
        self.assertIn("ليست إشارة دخول", message)

    def test_academy_rotation_contains_research_source_and_no_promise(self):
        paper = FakePaper()
        now = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
        while int(now.timestamp() // 3600) % 4 not in (1, 3):
            now = now.replace(hour=now.hour + 1)
        message = build_weekend_education_message(paper, now)
        self.assertIn("أكاديمية Laith V4", message)
        self.assertIn("أصل الفكرة", message)
        self.assertIn("ليست إشارة دخول", message)
        self.assertNotIn("مضمونة", message)

    def test_rotation_still_has_concrete_scenario_drill(self):
        paper = FakePaper()
        now = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
        while int(now.timestamp() // 3600) % 4 != 2:
            now = now.replace(hour=now.hour + 1)
        message = build_weekend_education_message(paper, now)
        self.assertIn("مثال افتراضي", message)
        self.assertIn("كيف نحللها", message)


if __name__ == "__main__":
    unittest.main()
