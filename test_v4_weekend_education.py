from datetime import datetime, timedelta, timezone
import unittest

from v4_weekend_education import (
    build_weekend_lesson,
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
        self.photos = []

    def send(self, message):
        self.messages.append(message)
        return True

    def send_photo(self, photo_bytes, caption=None):
        self.photos.append((photo_bytes, caption))
        return True


class FakePaper:
    def __init__(self, winners=None):
        self.winners = list(winners or [])

    def _paper_rows(self):
        return list(self.winners)

    def _quick_rows(self):
        return []


class WeekendEducationTests(unittest.TestCase):
    def test_window_starts_at_local_saturday_midnight(self):
        before_local_saturday = datetime(2026, 9, 18, 20, 59, tzinfo=UTC)
        local_saturday = datetime(2026, 9, 18, 21, 0, tzinfo=UTC)
        self.assertFalse(weekend_education_window(before_local_saturday))
        self.assertTrue(weekend_education_window(local_saturday))

    def test_window_stops_at_sunday_new_york_reopen(self):
        before_open = datetime(2026, 9, 20, 21, 59, tzinfo=UTC)
        at_open = datetime(2026, 9, 20, 22, 0, tzinfo=UTC)
        self.assertTrue(weekend_education_window(before_open))
        self.assertFalse(weekend_education_window(at_open))

    def test_lesson_has_multiple_parts_and_visuals(self):
        lesson = build_weekend_lesson(FakePaper(), 1)
        self.assertGreaterEqual(len(lesson["parts"]), 6)
        visuals = [p for p in lesson["parts"] if p.get("visual")]
        self.assertGreaterEqual(len(visuals), 2)
        self.assertIn("الدرس 1", lesson["parts"][0]["text"])
        self.assertIn("انتهى الدرس 1", lesson["parts"][-1]["text"])

    def test_first_part_sends_immediately_and_no_duplicate_before_five_minutes(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, start))
        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, start + timedelta(minutes=4, seconds=59)
        ))
        self.assertEqual(len(notifier.messages), 1)
        self.assertEqual(len(notifier.photos), 0)
        self.assertEqual(store.get("v4_weekend_lesson_state")["part_index"], 1)

    def test_second_part_arrives_after_five_minutes_with_image(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, start))
        self.assertTrue(maybe_send_weekend_education(
            store, notifier, paper, start + timedelta(minutes=5)
        ))
        self.assertEqual(len(notifier.photos), 1)
        photo, caption = notifier.photos[0]
        self.assertTrue(photo.startswith(b"\x89PNG"))
        self.assertIn("الجزء 2", caption)

    def test_complete_lesson_then_wait_full_hour(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        lesson = build_weekend_lesson(paper, 1)
        for index in range(len(lesson["parts"])):
            current = start + timedelta(minutes=5 * index)
            self.assertTrue(maybe_send_weekend_education(store, notifier, paper, current))

        state = store.get("v4_weekend_lesson_state")
        self.assertEqual(state["status"], "cooldown")
        self.assertEqual(store.get("v4_weekend_lesson_number"), 2)

        all_text = notifier.messages + [caption for _, caption in notifier.photos]
        self.assertTrue(any("انتهى الدرس 1" in text for text in all_text))
        self.assertTrue(any("انتظر الدرس التالي بعد ساعة" in text for text in all_text))

        finished = start + timedelta(minutes=5 * (len(lesson["parts"]) - 1))
        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(minutes=59, seconds=59)
        ))
        self.assertTrue(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(hours=1)
        ))
        all_text = notifier.messages + [caption for _, caption in notifier.photos]
        self.assertTrue(any("الدرس 2" in text for text in all_text))

    def test_progress_survives_repeated_calls_like_restart(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, start))
        saved = dict(store.get("v4_weekend_lesson_state"))
        self.assertEqual(saved["part_index"], 1)

        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, start + timedelta(minutes=2)
        ))
        self.assertEqual(store.get("v4_weekend_lesson_state")["part_index"], 1)

        self.assertTrue(maybe_send_weekend_education(
            store, notifier, paper, start + timedelta(minutes=5)
        ))
        self.assertEqual(store.get("v4_weekend_lesson_state")["part_index"], 2)

    def test_profitable_saved_trade_becomes_full_case_study(self):
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
        lesson = build_weekend_lesson(FakePaper([winner]), 4)
        self.assertEqual(lesson["kind"], "historical")
        joined = "\n".join(part["text"] for part in lesson["parts"])
        self.assertIn("تشريح صفقة V4 حقيقية", joined)
        self.assertIn("4300.00", joined)
        self.assertIn("+1.80R", joined)


if __name__ == "__main__":
    unittest.main()
