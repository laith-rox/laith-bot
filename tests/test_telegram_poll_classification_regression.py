"""Regression tests for secret-safe Telegram polling failure classification."""
import unittest
from unittest.mock import Mock

from transport import Telegram


class TelegramReadSafetyTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.telegram = Telegram("test-token-not-real", "123", session=self.session)

    def _response(self, status, payload):
        response = Mock()
        response.status_code = status
        response.json.return_value = payload
        self.session.get.return_value = response

    def test_conflicting_poller_is_classified_without_token(self):
        self._response(409, {"ok": False, "error_code": 409,
                             "description": "Conflict: terminated by other getUpdates request"})
        with self.assertRaisesRegex(RuntimeError, "^telegram_poll_conflict_or_webhook$") as raised:
            self.telegram.read("getUpdates", offset=10)
        self.assertNotIn("test-token-not-real", str(raised.exception))

    def test_unauthorized_token_is_classified_without_token(self):
        self._response(401, {"ok": False, "error_code": 401})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_unauthorized$"):
            self.telegram.read("getUpdates")

    def test_rate_limit_is_classified(self):
        self._response(429, {"ok": False, "error_code": 429})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_rate_limited$"):
            self.telegram.read("getUpdates")

    def test_http_unauthorized_overrides_misleading_json_conflict(self):
        self._response(401, {"ok": False, "error_code": 409})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_unauthorized$"):
            self.telegram.read("getUpdates")

    def test_http_conflict_overrides_misleading_json_unauthorized(self):
        self._response(409, {"ok": False, "error_code": 401})
        with self.assertRaisesRegex(RuntimeError, "^telegram_poll_conflict_or_webhook$"):
            self.telegram.read("getUpdates")

    def test_successful_poll_preserves_updates(self):
        updates = [{"update_id": 17, "message": {"text": "/status"}}]
        self._response(200, {"ok": True, "result": updates})
        self.assertEqual(self.telegram.read("getUpdates"), updates)

    def test_invalid_json_fails_closed(self):
        self._response(200, {})
        self.session.get.return_value.json.side_effect = ValueError("invalid JSON")
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_failed$"):
            self.telegram.read("getUpdates")


    def test_malformed_updates_result_rejected(self):
        self._response(200, {"ok": True, "result": {"update_id": 20}})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_invalid_result$"):
            self.telegram.read("getUpdates")

    def test_missing_result_fails_closed(self):
        self._response(200, {"ok": True})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_failed$"):
            self.telegram.read("getUpdates")

    def test_webhook_info_requires_object(self):
        self._response(200, {"ok": True, "result": []})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_invalid_result$"):
            self.telegram.read("getWebhookInfo")

    def test_non_object_response_fails_closed_without_token(self):
        self._response(200, ["unexpected", "response"])
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_rejected$") as raised:
            self.telegram.read("getUpdates")
        self.assertNotIn("test-token-not-real", str(raised.exception))

    def test_http_server_error_is_not_treated_as_valid_updates(self):
        self._response(503, {"ok": True, "result": [{"update_id": 99}]})
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_rejected$"):
            self.telegram.read("getUpdates")

    def test_network_timeout_is_classified_without_secret(self):
        import requests
        self.session.get.side_effect = requests.Timeout("connection timed out")
        with self.assertRaisesRegex(RuntimeError, "^telegram_read_failed$") as raised:
            self.telegram.read("getUpdates", offset=7)
        self.assertNotIn("test-token-not-real", str(raised.exception))

if __name__ == "__main__":
    unittest.main()
