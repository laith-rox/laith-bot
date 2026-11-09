"""Regression coverage for fail-closed Telegram read authorization and method allowlist."""
import unittest
from unittest.mock import Mock

from transport import Telegram


class TelegramReadBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.telegram = Telegram("fake-secret-token", "123", session=self.session)

    def response(self, status, payload):
        result = Mock()
        result.status_code = status
        result.json.return_value = payload
        self.session.get.return_value = result

    def test_unsupported_write_method_cannot_use_read_transport(self):
        with self.assertRaisesRegex(ValueError, "^unsupported_read_method$"):
            self.telegram.read("deleteWebhook")
        self.session.get.assert_not_called()

    def test_forbidden_is_classified_without_leaking_secret(self):
        self.response(403, {"ok": False, "error_code": 403, "description": "forbidden"})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_unauthorized$") as caught:
            self.telegram.read("getUpdates")
        self.assertNotIn("fake-secret-token", str(caught.exception))

    def test_success_http_without_explicit_ok_is_rejected(self):
        self.response(200, {"result": [{"update_id": 3}]})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_rejected$"):
            self.telegram.read("getUpdates")

    def test_wrong_result_shape_on_get_me_is_rejected(self):
        self.response(200, {"ok": True, "result": []})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_invalid_result$"):
            self.telegram.read("getMe")


if __name__ == "__main__":
    unittest.main()
