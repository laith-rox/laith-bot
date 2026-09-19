from datetime import datetime, timedelta, timezone
import unittest

from v4_weekend_education import (
    build_weekend_lesson,
    maybe_send_weekend_education,
    weekend_education_window,
    tonight_intensive_window,
)
from v4_global_academy import academy_lesson, curriculum_size

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
        self.assertIn("جولة السوق #1", lesson["parts"][0]["text"])
        self.assertIn("خلصت جولة السوق #1", lesson["parts"][-1]["text"])

    def test_first_part_sends_immediately_and_no_duplicate_before_five_minutes(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, start))
        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, start + timedelta(minutes=4, seconds=59)
        ))
        self.assertEqual(len(notifier.messages), 0)
        self.assertEqual(len(notifier.photos), 1)
        first_photo, first_caption = notifier.photos[0]
        self.assertTrue(first_photo.startswith(b"\x89PNG"))
        self.assertIn("نوع المثال في الصورة", first_caption)
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
        self.assertIn("جولة السوق #1", caption)

    def test_tonight_intensive_window_only_before_local_midnight(self):
        self.assertTrue(tonight_intensive_window(datetime(2026, 9, 19, 20, 30, tzinfo=UTC)))
        self.assertFalse(tonight_intensive_window(datetime(2026, 9, 19, 21, 0, tzinfo=UTC)))
        self.assertFalse(tonight_intensive_window(datetime(2026, 9, 20, 20, 30, tzinfo=UTC)))

    def test_tonight_next_lesson_starts_after_five_minutes_not_one_hour(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 20, 20, tzinfo=UTC)

        lesson = build_weekend_lesson(paper, 1)
        for index in range(len(lesson["parts"])):
            self.assertTrue(maybe_send_weekend_education(
                store, notifier, paper, start + timedelta(minutes=5 * index)
            ))

        finished = start + timedelta(minutes=5 * (len(lesson["parts"]) - 1))
        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(minutes=4, seconds=59)
        ))
        self.assertTrue(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(minutes=5)
        ))
        all_text = notifier.messages + [caption for _, caption in notifier.photos]
        self.assertTrue(any("جولة السوق #2" in text for text in all_text))

    def test_after_midnight_returns_to_normal_one_hour_cooldown(self):
        store = FakeStore()
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 21, 5, tzinfo=UTC)

        lesson = build_weekend_lesson(paper, 1)
        for index in range(len(lesson["parts"])):
            self.assertTrue(maybe_send_weekend_education(
                store, notifier, paper, start + timedelta(minutes=5 * index)
            ))

        finished = start + timedelta(minutes=5 * (len(lesson["parts"]) - 1))
        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(minutes=5)
        ))
        self.assertTrue(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(hours=1)
        ))

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
        self.assertTrue(any("خلصت جولة السوق #1" in text for text in all_text))
        self.assertTrue(any("الجولة الجاية" in text for text in all_text))

        finished = start + timedelta(minutes=5 * (len(lesson["parts"]) - 1))
        self.assertFalse(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(minutes=59, seconds=59)
        ))
        self.assertTrue(maybe_send_weekend_education(
            store, notifier, paper, finished + timedelta(hours=1)
        ))
        all_text = notifier.messages + [caption for _, caption in notifier.photos]
        self.assertTrue(any("جولة السوق #2" in text for text in all_text))

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

    def test_lesson_style_is_story_not_classroom(self):
        lesson = build_weekend_lesson(FakePaper(), 1)
        joined = "\n".join(part["text"] for part in lesson["parts"])
        self.assertIn("🎬", joined)
        self.assertIn("هون الفكرة ببساطة", joined)
        self.assertIn("هسا شوف متى بنغلط", joined)
        self.assertIn("هسا دورك إنت", joined)
        self.assertNotIn("الجزء 3 — كيف تطبقها عمليًا", joined)
        self.assertNotIn("تدريب المتداول", joined)

    def test_style_update_preserves_lesson_number(self):
        store = FakeStore()
        store.set("v4_weekend_curriculum_version", 3)
        store.set("v4_weekend_lesson_style_version", 0)
        store.set("v4_weekend_lesson_number", 6)
        store.set("v4_weekend_lesson_state", {"status": "active", "part_index": 2})
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, start))
        self.assertEqual(store.get("v4_weekend_lesson_number"), 6)
        self.assertEqual(store.get("v4_weekend_lesson_style_version"), 3)
        sent = "\n".join(notifier.messages + [x[1] for x in notifier.photos])
        self.assertIn("جولة السوق #6", sent)

    def test_visible_first_lesson_uses_arabic_terms(self):
        lesson = build_weekend_lesson(FakePaper(), 1)
        joined = "\n".join(part["text"] for part in lesson["parts"])
        self.assertNotIn("BUY", joined)
        self.assertNotIn("SELL", joined)
        self.assertNotIn("M15", joined)
        self.assertNotIn("H1", joined)
        self.assertIn("شراء", joined)
        self.assertIn("فريم ١٥ دقيقة", joined)
        self.assertIn("فريم الساعة", joined)

    def test_first_visual_is_explicit_arabic_buy_sell_or_wait(self):
        lesson = build_weekend_lesson(FakePaper(), 1)
        first = lesson["parts"][0]
        self.assertIn(first.get("visual_side"), ("شراء", "بيع", "انتظار", "شرح"))
        self.assertIn("نوع المثال في الصورة", first["text"])
        self.assertNotIn("ENTRY", first["text"])
        self.assertNotIn("SL", first["text"])
        self.assertNotIn("TP", first["text"])

    def test_correction_and_breakout_have_dedicated_visual_families(self):
        correction = academy_lesson(4)
        breakout = academy_lesson(5)
        self.assertIn("التصحيح", correction["title"])
        self.assertIn("اختراق", breakout["title"])
        correction_lesson = build_weekend_lesson(FakePaper(), 5)
        breakout_lesson = build_weekend_lesson(FakePaper(), 6)
        self.assertEqual(correction_lesson["parts"][0]["visual"], "correction")
        self.assertEqual(breakout_lesson["parts"][0]["visual"], "breakout")
        self.assertEqual(correction_lesson["parts"][3]["visual_side"], "انتظار")
        self.assertEqual(breakout_lesson["parts"][3]["visual_side"], "انتظار")

    def test_curriculum_starts_fast_and_direct(self):
        first = academy_lesson(0)
        self.assertIn("كيف تقرأ سوق الذهب", first["title"])
        self.assertIn("قراءة السوق مباشرة", first["level"])

        second = academy_lesson(1)
        self.assertIn("الشمعة", second["title"])

        eighth = academy_lesson(7)
        self.assertIn("صفقتان بنفس الاتجاه", eighth["title"])

        later = academy_lesson(9)
        self.assertTrue(later["level"].startswith("المستوى 4"))

    def test_no_case_study_jumps_ahead_of_curriculum(self):
        paper = FakePaper([{
            "id": "winner",
            "status": "closed",
            "side": "BUY",
            "entry": 4300,
            "stop": 4295,
            "target": 4310,
            "r": 1.0,
        }])
        for lesson_number in (1, 2, 4, 10, curriculum_size()):
            lesson = build_weekend_lesson(paper, lesson_number)
            self.assertEqual(lesson["kind"], "curriculum")

    def test_curriculum_version_resets_academy_only_to_lesson_one(self):
        store = FakeStore()
        store.set("v4_weekend_curriculum_version", 1)
        store.set("v4_weekend_lesson_number", 17)
        store.set("v4_weekend_lesson_state", {"status": "active", "part_index": 3})
        store.set("unrelated_trade_state", {"keep": True})
        notifier = FakeNotifier()
        paper = FakePaper()
        start = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)

        self.assertTrue(maybe_send_weekend_education(store, notifier, paper, start))
        self.assertEqual(store.get("v4_weekend_curriculum_version"), 3)
        self.assertEqual(store.get("v4_weekend_lesson_number"), 1)
        self.assertEqual(store.get("unrelated_trade_state"), {"keep": True})
        sent = "\n".join(notifier.messages + [x[1] for x in notifier.photos])
        self.assertIn("جولة السوق #1", sent)
        self.assertIn("كيف تقرأ سوق الذهب", sent)

    def test_profitable_saved_trade_becomes_full_case_study_after_graduation(self):
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
        lesson_number = curriculum_size() + 3
        lesson = build_weekend_lesson(FakePaper([winner]), lesson_number)
        self.assertEqual(lesson["kind"], "historical")
        joined = "\n".join(part["text"] for part in lesson["parts"])
        self.assertIn("تشريح صفقة V4 حقيقية", joined)
        self.assertIn("4300.00", joined)
        self.assertIn("+1.80R", joined)


if __name__ == "__main__":
    unittest.main()
