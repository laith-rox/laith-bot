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


if __name__ == "__main__":
    unittest.main()
