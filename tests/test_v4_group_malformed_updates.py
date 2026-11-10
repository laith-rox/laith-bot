"""Malformed Telegram updates must not crash the group poller or rewind its cursor."""
import unittest
from unittest.mock import Mock

from v4_group_telegram import V4Telegram


class GroupMalformedUpdateTests(unittest.TestCase):
    def _poll(self, updates, initial=0):
        state = {"v4_telegram_update_offset": initial}
        store = Mock()
        store.get.side_effect = lambda key, default=None: state.get(key, default)
        store.set.side_effect = lambda key, value: state.__setitem__(key, value)
        client = Mock()
        client.read.return_value = updates
        bot = V4Telegram.__new__(V4Telegram)
        bot.client = client
        bot.store = store
        bot.poll()
        return state["v4_telegram_update_offset"]

    def test_message_as_string_does_not_crash(self):
        self.assertEqual(self._poll([{"update_id": 4, "message": "bad"}]), 5)

    def test_chat_as_list_does_not_crash(self):
        self.assertEqual(self._poll([{"update_id": 8, "message": {
            "chat": [], "from": {"id": 1}, "text": "/status"}}]), 9)

    def test_text_as_dict_does_not_crash(self):
        self.assertEqual(self._poll([{"update_id": 12, "message": {
            "chat": {"id": 1}, "from": {"id": 1}, "text": {"unexpected": 1}}}]), 13)

    def test_malformed_out_of_order_cannot_rewind_cursor(self):
        updates = [{"update_id": 9, "message": None},
                   {"update_id": 7, "message": {"chat": None}}]
        self.assertEqual(self._poll(updates, initial=9), 10)

    def test_non_object_update_does_not_advance_cursor(self):
        self.assertEqual(self._poll(["bad"], initial=6), 6)


if __name__ == "__main__":
    unittest.main()
