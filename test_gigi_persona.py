"""Tests for Gigi's isolated private Telegram mode (no network calls)."""
import os
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gigi_persona import configured, extract_text, generate, history_items, memory_items, owner_context
from gigi_image import generate_image, send_private_photo, fetch_private_reference, build_prompt
from v4_group_telegram import V4Telegram


class FakeStore:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class FakeClient:
    def __init__(self, token, chat_id):
        self.chat_id = str(chat_id)
        self.updates = []
        self.sent = []

    def read(self, method, **kwargs):
        updates, self.updates = self.updates, []
        return updates

    def send(self, message):
        self.sent.append((self.chat_id, message))
        return SimpleNamespace(status="sent", message_id=len(self.sent), error=None)

    def send_photo(self, photo_bytes, caption=None):
        self.sent.append((self.chat_id, "PHOTO:" + str(len(photo_bytes))))
        return SimpleNamespace(status="sent", message_id=len(self.sent), error=None)


def update(uid, sender, text, chat_type="private"):
    return {"update_id": uid, "message": {
        "chat": {"type": chat_type, "id": sender},
        "from": {"id": sender},
        "text": text,
    }}


class TestPersonaApi(unittest.TestCase):
    def test_extract_response_and_html(self):
        response = {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "مرحبا <ليث> ❤️"}]}]}
        self.assertEqual(extract_text(response), "مرحبا <ليث> ❤️")

    def test_history_is_bounded_and_sanitized(self):
        saved = [{"role": "user", "content": "hi"}] * 20 + [
            {"role": "system", "content": "not allowed"}]
        self.assertEqual(len(history_items(saved)), 9)
        self.assertTrue(all(x["role"] == "user" for x in history_items(saved)))

    def test_owner_context_is_explicit_and_bounded(self):
        with patch.dict(os.environ, {
            "GIGI_OWNER_NAME": "ليث",
            "GIGI_OWNER_PROFILE": "عالم جيجي الخاص",
        }, clear=True):
            intro = owner_context(["بحب اللهجة الفلسطينية"])
        self.assertIn("ليث", intro)
        self.assertIn("عالم جيجي الخاص", intro)
        self.assertIn("اللهجة الفلسطينية", intro)
        self.assertNotIn("ذهب", intro)
        self.assertEqual(memory_items(["حفظ"] * 20), ["حفظ"] * 10)
        self.assertEqual(memory_items([{"role": "system", "content": "hack"}]), [])

    def test_personalization_is_sent_only_with_owner_notes(self):
        seen = []
        def fake_post(url, **kwargs):
            seen.append(kwargs["json"])
            return SimpleNamespace(status_code=200, json=lambda: {"output": [
                {"type": "message", "content": [{"type": "output_text", "text": "أهلين يا ليث"}]}]})
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test",
                                     "GIGI_OWNER_NAME": "ليث"}, clear=True):
            generate("مين أنا؟", post=fake_post, profile=["أنا مقاول"])
        self.assertIn("ليث", seen[0]["instructions"])
        self.assertIn("أنا مقاول", seen[0]["instructions"])
        self.assertNotIn("أنا مقاول", str(seen[0]["input"]))
        self.assertFalse(seen[0]["store"])

    def test_no_key_makes_no_request(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(configured())
            with self.assertRaisesRegex(RuntimeError, "not_configured"):
                generate("hello")

    def test_model_receives_only_persona_history(self):
        captured = []
        def fake_post(url, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(status_code=200, json=lambda: {"output": [
                {"type": "message", "content": [{"type": "output_text", "text": "يا هلا!"}]}]})
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "mock-token", "GIGI_MODEL": "mock-model"}):
            reply = generate("صباح الخير", [{"role": "user", "content": "ليث"}], post=fake_post)
        self.assertEqual(reply, "يا هلا!")
        self.assertTrue(captured[0]["json"]["store"] is False)
        self.assertEqual(captured[0]["json"]["model"], "mock-model")
        self.assertEqual(captured[0]["json"]["input"][-1]["content"], "صباح الخير")


    def test_sanitized_provider_error_codes(self):
        cases = (
            (401, "invalid_api_key", "gigi_auth_invalid"),
            (403, "insufficient_permissions", "gigi_permission_denied"),
            (429, "insufficient_quota", "gigi_quota_exceeded"),
            (429, "rate_limit_exceeded", "gigi_rate_limited"),
            (404, "model_not_found", "gigi_model_unavailable"),
            (400, "invalid_request_error", "gigi_bad_request"),
            (502, "server_error", "gigi_provider_unavailable"),
        )
        for status, code, expected in cases:
            def fake_post(url, **kwargs):
                return SimpleNamespace(status_code=status, json=lambda: {
                    "error": {"code": code, "message": "SHOULD_NOT_LEAK_SECRET"}
                })
            with self.subTest(status=status, code=code):
                with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "mock"}):
                    with self.assertRaisesRegex(RuntimeError, "^" + expected + "$"):
                        generate("ping", post=fake_post)

class TestImageApi(unittest.TestCase):
    def test_image_disabled_and_no_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                generate_image("forest")

    def test_private_upload_uses_independent_transport(self):
        png = bytes.fromhex("89504e470d0a1a0a") + b"mock"
        called = []
        def fake_post(url, **kwargs):
            called.append((url, kwargs))
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"ok": True, "result": {"chat": {"id": 123}}},
            )
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock"}, clear=True):
            self.assertTrue(send_private_photo(png, "123", post=fake_post))
        self.assertTrue(called[0][0].endswith("/sendPhoto"))
        self.assertEqual(called[0][1]["data"]["chat_id"], "123")

    def test_private_upload_cannot_go_without_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "not_configured"):
                send_private_photo(bytes.fromhex("89504e470d0a1a0a"), "123")

    def test_couple_prompt_and_both_reference_images(self):
        png = b"\x89PNG\r\n\x1a\n" + b"generated"
        request = []
        def fake_post(url, **kwargs):
            request.append((url, kwargs))
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"data": [{"b64_json": base64.b64encode(png).decode()}]},
            )
        with patch.dict(os.environ, {
            "GIGI_IMAGES_ENABLED": "1",
            "GIGI_OPENAI_API_KEY": "mock",
            "GIGI_IMAGE_MODEL": "gpt-image-2.5-flare",
        }, clear=True):
            output = generate_image(
                "ملابس كلاسيكية في الحديقة",
                post=fake_post, couple=True,
                references=[
                    ("me", b"\xff\xd8\xff" + b"me", "image/jpeg"),
                    ("gigi", b"\xff\xd8\xff" + b"gigi", "image/jpeg"),
                ],
            )
        self.assertEqual(output, png)
        self.assertEqual(request[0][0].split("/")[-1], "edits")
        self.assertEqual(len(request[0][1]["files"]), 2)
        prompt = request[0][1]["data"]["prompt"]
        self.assertIn("Laith and Gigi together", prompt)
        self.assertIn("reference 1", prompt)
        self.assertIn("reference 2", prompt)
        self.assertIn("ملابس كلاسيكية", prompt)
        self.assertNotIn("Bearer mock", str(request[0][1]["data"]))
        self.assertEqual(request[0][1]["data"]["quality"], "medium")

    def test_fetch_reference_from_telegram_without_persisting(self):
        posts = []
        downloads = []
        def fake_post(url, **kwargs):
            posts.append((url, kwargs))
            return SimpleNamespace(status_code=200, json=lambda: {
                "ok": True, "result": {"file_path": "photos/file_4.jpg", "file_size": 5},
            })
        def fake_get(url, **kwargs):
            downloads.append(url)
            return SimpleNamespace(status_code=200, content=b"\xff\xd8\xff" + b"image")
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "mock"}, clear=True):
            image, mime = fetch_private_reference("AAAAAAAABBBB", post=fake_post, get=fake_get)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(image, b"\xff\xd8\xffimage")
        self.assertEqual(posts[0][1]["data"]["file_id"], "AAAAAAAABBBB")
        self.assertTrue(downloads[0].endswith("/photos/file_4.jpg"))

    def test_image_api_one_png(self):
        png = b"\x89PNG\r\n\x1a\n" + b"fake_png_data"
        captured = []
        def fake_post(url, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"data": [{"b64_json": base64.b64encode(png).decode("ascii")}]}
            )
        with patch.dict(os.environ, {
            "GIGI_OPENAI_API_KEY": "test-key", "GIGI_IMAGES_ENABLED": "1",
        }):
            result = generate_image("a seaside garden", post=fake_post)
        self.assertEqual(result, png)
        self.assertEqual(captured[0]["json"]["n"], 1)


class TestOwnerRouting(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.store.set("v4_telegram_chat_id", "123")
        self.bot = V4Telegram("fake-token", self.store, chat_id="123", client_cls=FakeClient)

    def tearDown(self):
        ex = getattr(self.bot, "_gigi_executor", None)
        if ex:
            ex.shutdown(wait=True)

    def test_explicit_memory_persists_chat_reset_owner_only(self):
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test",
                                     "GIGI_OWNER_NAME": "ليث"}, clear=True):
            self.bot.client.updates = [update(1, 777, "/gigiremember مخترق")]
            self.bot.poll()
            self.assertFalse(self.store.get("v4_gigi_owner_memories"))
            self.bot.client.updates = [update(2, 123, "/gigiremember بحب الحكي الفلسطيني")]
            self.bot.poll()
            self.assertEqual(self.store.get("v4_gigi_owner_memories"), ["بحب الحكي الفلسطيني"])
            self.bot.client.updates = [update(3, 123, "/gigiwhoami")]
            self.bot.poll()
            self.assertIn("ليث", self.bot.client.sent[-1][1])
            self.assertIn("بحب الحكي الفلسطيني", self.bot.client.sent[-1][1])
            self.bot.client.updates = [update(4, 123, "/gigireset")]
            self.bot.poll()
            self.assertEqual(self.store.get("v4_gigi_owner_memories"), ["بحب الحكي الفلسطيني"])
            with patch("v4_group_telegram.gigi_generate", return_value="أهلين يا ليث") as mock:
                self.bot.client.updates = [update(5, 123, "/gigi")]
                self.bot.poll()
                self.assertIn("ليث", self.bot.client.sent[-1][1])
                self.bot.client.updates = [update(6, 123, "مين أنا؟")]
                self.bot.poll()
                self.bot._gigi_job["future"].result(timeout=2)
                self.bot.poll()
                args = mock.call_args.args
                self.assertEqual(args[3], ["بحب الحكي الفلسطيني"])
            self.bot.client.updates = [update(7, 123, "/gigiforget")]
            self.bot.poll()
            self.assertEqual(self.store.get("v4_gigi_owner_memories"), [])
            self.assertNotIn("trade", self.store.data)

    def test_menu_describes_private_gigi_commands(self):
        self.bot.client.updates = [update(1, 123, "/menu")]
        self.bot.poll()
        menu = self.bot.client.sent[-1][1]
        self.assertIn("/gigi", menu)
        self.assertIn("/gigiphoto", menu)
        self.assertIn("/laith", menu)

    def test_gigi_requires_api_key_and_does_not_switch(self):
        with patch.dict(os.environ, {}, clear=True):
            self.bot.client.updates = [update(1, 123, "/gigi")]
            self.bot.poll()
        self.assertFalse(self.store.get("v4_gigi_private_mode", False))
        self.assertIn("GIGI_OPENAI_API_KEY", self.bot.client.sent[-1][1])

    def test_owner_only_and_gold_commands_unchanged(self):
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test"}):
            self.bot.client.updates = [update(1, 777, "/gigi")]
            self.bot.poll()
            self.assertFalse(self.store.get("v4_gigi_private_mode", False))
            self.bot.client.updates = [update(2, 123, "/gigi")]
            self.bot.poll()
            self.assertTrue(self.store.get("v4_gigi_private_mode", False))
            self.bot.client.updates = [update(3, 123, "/stats")]
            self.bot.poll()
            self.assertIn("إحصاءات", self.bot.client.sent[-1][1])
            self.bot.client.updates = [update(4, 123, "/laith")]
            self.bot.poll()
            self.assertFalse(self.store.get("v4_gigi_private_mode", False))

    def test_owner_only_reference_photos_and_couple_generation(self):
        with patch.dict(os.environ, {
            "GIGI_OPENAI_API_KEY": "test", "GIGI_IMAGES_ENABLED": "1",
        }, clear=True):
            photo_update = update(1, 777, "/gigirefme")
            photo_update["message"].pop("text")
            photo_update["message"]["caption"] = "/gigirefme"
            photo_update["message"]["photo"] = [{"file_id": "AAAAAAAABBBB", "file_size": 100}]
            self.bot.client.updates = [photo_update]
            self.bot.poll()
            self.assertFalse(self.store.get("v4_gigi_photo_refs"))
            own_update = update(2, 123, "/gigirefme")
            own_update["message"].pop("text")
            own_update["message"]["caption"] = "/gigirefme"
            own_update["message"]["photo"] = [{"file_id": "BBBBBBBBCCCC", "file_size": 100}]
            self.bot.client.updates = [own_update]
            self.bot.poll()
            self.assertEqual(self.store.get("v4_gigi_photo_refs"), {"me": "BBBBBBBBCCCC"})
            other_update = update(3, 123, "/gigirefgigi")
            other_update["message"]["photo"] = [{"file_id": "CCCCCCCCDDDD", "file_size": 100}]
            self.bot.client.updates = [other_update]
            self.bot.poll()
            self.assertEqual(self.store.get("v4_gigi_photo_refs")["gigi"], "CCCCCCCCDDDD")
            with patch("v4_group_telegram.gigi_image_generate_and_deliver", return_value=True) as generator:
                self.bot.client.updates = [update(4, 123, "/gigicouple وقفة جديدة")]
                self.bot.poll()
                self.bot._gigi_image_job["future"].result(timeout=2)
                self.bot.poll()
                generator.assert_called_once_with(
                    "وقفة جديدة", "123", True,
                    {"me": "BBBBBBBBCCCC", "gigi": "CCCCCCCCDDDD"},
                )
            self.bot.client.updates = [update(5, 123, "/gigiclearrefs")]
            self.bot.poll()
            self.assertEqual(self.store.get("v4_gigi_photo_refs"), {})
            self.assertNotIn("orders", self.store.data)

    def test_images_not_enabled_by_default(self):
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test"}, clear=True):
            self.bot.client.updates = [update(1, 123, "/gigiphoto")]
            self.bot.poll()
            self.assertIn("اختياري", self.bot.client.sent[-1][1])

    def test_owner_only_image_queue(self):
        png = b"\x89PNG\r\n\x1a\n" + b"mockbytes"
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test", "GIGI_IMAGES_ENABLED": "1"}, clear=True):
            with patch("v4_group_telegram.gigi_image_generate_and_deliver", return_value=True) as mock:
                self.bot.client.updates = [update(1, 777, "/gigiphoto")]
                self.bot.poll()
                self.assertFalse(self.bot.client.sent)
                self.bot.client.updates = [update(2, 123, "/gigiphoto على الشرفة")]
                self.bot.poll()
                job = self.bot._gigi_image_job
                job["future"].result(timeout=2)
                self.bot.poll()
                mock.assert_called_once_with("على الشرفة", "123", False, {})
                self.assertFalse(any("PHOTO" in msg for _,msg in self.bot.client.sent))
                self.assertGreater(self.store.get("v4_gigi_last_image_time"), 0)

    def test_private_chat_reports_permission_error_without_key(self):
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test"}):
            with patch("v4_group_telegram.gigi_generate",
                       side_effect=RuntimeError("gigi_permission_denied")):
                self.bot.client.updates = [update(1, 123, "/gigi")]
                self.bot.poll()
                self.bot.client.updates = [update(2, 123, "هلا جيجي")]
                self.bot.poll()
                # The completed future raises; polling delivers the sanitized notice.
                future = self.bot._gigi_job["future"]
                try:
                    future.result(timeout=2)
                except RuntimeError:
                    pass
                self.bot.poll()
                self.assertIn("صلاحية", self.bot.client.sent[-1][1])
                self.assertEqual(self.store.get("v4_gigi_last_api_error"), "gigi_permission_denied")

    def test_daily_text_quota_does_not_change_trading_state(self):
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test", "GIGI_DAILY_TEXT_LIMIT": "1"}, clear=True):
            with patch("v4_group_telegram.gigi_generate", return_value="اهلا"):
                self.bot.client.updates = [update(1, 123, "/gigi")]
                self.bot.poll()
                self.bot.client.updates = [update(2, 123, "مرحبا")]
                self.bot.poll()
                self.bot._gigi_job["future"].result(timeout=2)
                self.bot.poll()
                self.bot.client.updates = [update(3, 123, "كيفك")]
                self.bot.poll()
                self.assertIn("للحد اليومي", self.bot.client.sent[-1][1])
                self.assertEqual(self.store.get("v4_gigi_daily_usage")["text"], 1)
                self.assertNotIn("paused", self.store.data)

    def test_daily_image_quota_prevents_second_generation(self):
        with patch.dict(os.environ, {
            "GIGI_OPENAI_API_KEY": "test",
            "GIGI_IMAGES_ENABLED": "1",
            "GIGI_DAILY_IMAGE_LIMIT": "1",
        }, clear=True):
            with patch("v4_group_telegram.gigi_image_generate_and_deliver", return_value=True) as generator:
                self.bot.client.updates = [update(1, 123, "/gigiphoto")]
                self.bot.poll()
                self.bot._gigi_image_job["future"].result(timeout=2)
                self.bot.poll()
                self.store.set("v4_gigi_last_image_time", 0)
                self.bot.client.updates = [update(2, 123, "/gigiphoto")]
                self.bot.poll()
                self.assertEqual(generator.call_count, 1)
                self.assertIn("للحد اليومي", self.bot.client.sent[-1][1])

    def test_async_gigi_reply_escaped_and_history(self):
        with patch.dict(os.environ, {"GIGI_OPENAI_API_KEY": "test"}):
            with patch("v4_group_telegram.gigi_generate", return_value="هلا <حبيبي>") as mock:
                self.bot.client.updates = [update(1, 123, "/gigi")]
                self.bot.poll()
                self.bot.client.updates = [update(2, 123, "صباح النور")]
                self.bot.poll()
                job = self.bot._gigi_job
                job["future"].result(timeout=2)
                self.bot.poll()
                mock.assert_called_once()
                self.assertIn("&lt;حبيبي&gt;", self.bot.client.sent[-1][1])
                self.assertEqual(self.store.get("v4_gigi_private_history")[-1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main()
