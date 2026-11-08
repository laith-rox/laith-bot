"""Regression: overlapping Telegram updates must not rewind persisted cursor."""
import unittest
from v4_telegram import V4Telegram as PrivateTelegram
from v4_group_telegram import V4Telegram as GroupTelegram


class MemoryStore:
    def __init__(self):
        self.data = {"v4_telegram_chat_id": "123", "v4_telegram_update_offset": 101}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class FakeTelegram:
    def __init__(self, token, chat_id):
        self.chat_id = chat_id

    def read(self, method, **params):
        return [
            {"update_id": 98, "message": {}},
            {"update_id": 100, "message": {}},
            {"update_id": 99, "message": {}},
            {"update_id": True, "message": {}},
            {"update_id": 102, "message": {}},
            {"update_id": 101, "message": {}},
        ]


class TelegramCursorTests(unittest.TestCase):
    def test_private_cursor_is_monotonic(self):
        store = MemoryStore()
        PrivateTelegram("fake", store, client_cls=FakeTelegram).poll()
        self.assertEqual(store.get("v4_telegram_update_offset"), 103)

    def test_group_cursor_is_monotonic(self):
        store = MemoryStore()
        GroupTelegram("fake", store, client_cls=FakeTelegram).poll()
        self.assertEqual(store.get("v4_telegram_update_offset"), 103)


    def test_replayed_group_command_is_not_executed(self):
        store = MemoryStore()
        class ReplayClient(FakeTelegram):
            sent = []
            def read(self, method, **params):
                return [{"update_id": 100, "message": {
                    "chat": {"id": -456, "type": "supergroup"},
                    "from": {"id": 123}, "text": "/group"}}]
            def send(self, message):
                self.sent.append(message)
        ReplayClient.sent = []
        GroupTelegram("fake", store, client_cls=ReplayClient).poll()
        self.assertIsNone(store.get("v4_telegram_group_id"))
        self.assertEqual(ReplayClient.sent, [])
        self.assertEqual(store.get("v4_telegram_update_offset"), 101)

    def test_new_group_command_executes_once(self):
        store = MemoryStore()
        class NewClient(FakeTelegram):
            sent = []
            def read(self, method, **params):
                return [{"update_id": 101, "message": {
                    "chat": {"id": -456, "type": "supergroup"},
                    "from": {"id": 123}, "text": "/group"}}]
            def send(self, message):
                self.sent.append(message)
        NewClient.sent = []
        bot = GroupTelegram("fake", store, client_cls=NewClient)
        bot.poll()
        bot.poll()
        self.assertEqual(store.get("v4_telegram_group_id"), "-456")
        self.assertEqual(len(NewClient.sent), 1)
        self.assertEqual(store.get("v4_telegram_update_offset"), 102)


if __name__ == "__main__":
    unittest.main()
