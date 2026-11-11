"""Tests for Gigi's isolated private Telegram mode (no network calls)."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from gigi_persona import configured, extract_text, generate, history_items
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


class TestOwnerRouting(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.store.set("v4_telegram_chat_id", "123")
        self.bot = V4Telegram("fake-token", self.store, chat_id="123", client_cls=FakeClient)

    def tearDown(self):
        ex = getattr(self.bot, "_gigi_executor", None)
        if ex:
            ex.shutdown(wait=True)

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
