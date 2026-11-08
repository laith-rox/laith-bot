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


if __name__ == "__main__":
    unittest.main()
