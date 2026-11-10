import tempfile
import unittest
from pathlib import Path

from storage import Store
from v4_group_telegram import V4Telegram


class Outcome:
    status = "sent"
    message_id = 1
    error = None


class FakeTelegram:
    updates = []

    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.sent = []

    def read(self, method, **kwargs):
        result = list(self.updates)
        self.updates = []
        return result

    def send(self, message):
        self.sent.append((str(self.chat_id), message))
        return Outcome()


class GroupTelegramTests(unittest.TestCase):
    def make(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "db.sqlite")
        store.set("v4_telegram_chat_id", "111")
        tg = V4Telegram("token", store, client_cls=FakeTelegram)
        return tmp, store, tg

    def test_paired_owner_can_bind_group_and_automatic_alerts_go_group_only(self):
        tmp, store, tg = self.make()
        try:
            tg.client.updates = [{
                "update_id": 7,
                "message": {
                    "chat": {"id": -999, "type": "supergroup"},
                    "from": {"id": 111},
                    "text": "/group",
                },
            }]
            tg.poll()
            self.assertEqual(store.get("v4_telegram_group_id"), "-999")
            tg.client.sent.clear()
            self.assertTrue(tg.send("signal"))
            self.assertEqual([x[0] for x in tg.client.sent], ["-999"])
        finally:
            store.close(); tmp.cleanup()

    def test_private_is_fallback_when_no_group_is_bound(self):
        tmp, store, tg = self.make()
        try:
            self.assertFalse(store.get("v4_telegram_group_id"))
            self.assertTrue(tg.send("signal"))
            self.assertEqual([x[0] for x in tg.client.sent], ["111"])
        finally:
            store.close(); tmp.cleanup()

    def test_poll_failure_preserves_offset_and_existing_group(self):
        tmp, store, tg = self.make()
        try:
            store.set("v4_telegram_update_offset", 42)
            store.set("v4_telegram_group_id", "-999")

            def rejected(*args, **kwargs):
                raise RuntimeError("telegram_poll_conflict_or_webhook")

            tg.client.read = rejected
            tg.poll()
            self.assertEqual(store.get("v4_telegram_update_offset"), 42)
            self.assertEqual(store.get("v4_telegram_group_id"), "-999")
            self.assertTrue(tg.send("BTC wait"))
            self.assertEqual(tg.client.sent[-1], ("-999", "BTC wait"))
        finally:
            store.close(); tmp.cleanup()

    def test_other_member_cannot_bind_group(self):
        tmp, store, tg = self.make()
        try:
            tg.client.updates = [{
                "update_id": 8,
                "message": {
                    "chat": {"id": -888, "type": "group"},
                    "from": {"id": 222},
                    "text": "/group",
                },
            }]
            tg.poll()
            self.assertFalse(store.get("v4_telegram_group_id"))
        finally:
            store.close(); tmp.cleanup()


class TelegramReadDiagnosticsTests(unittest.TestCase):
    def test_poll_conflict_is_classified_without_exposing_token(self):
        from transport import Telegram

        class Response:
            status_code = 409
            def json(self):
                return {"ok": False, "error_code": 409, "description": "Conflict: secret-token"}

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        client = Telegram("secret-token", "111", session=Session())
        with self.assertRaisesRegex(RuntimeError, "^telegram_poll_conflict_or_webhook$") as caught:
            client.read("getUpdates", offset=0)
        self.assertNotIn("secret-token", str(caught.exception))

    def test_unauthorized_is_classified_without_exposing_token(self):
        from transport import Telegram

        class Response:
            status_code = 401
            def json(self):
                return {"ok": False, "error_code": 401}

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        with self.assertRaisesRegex(RuntimeError, "^telegram_read_unauthorized$"):
            Telegram("secret-token", "111", session=Session()).read("getUpdates")


if __name__ == "__main__":
    unittest.main()
