"""Regression checks for safe Telegram read diagnostics (no real network)."""
from unittest.mock import Mock

import pytest

from transport import Telegram


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (409, "telegram_poll_conflict_or_webhook"),
        (401, "telegram_read_unauthorized"),
        (403, "telegram_read_unauthorized"),
        (429, "telegram_read_rate_limited"),
        (400, "telegram_read_rejected"),
    ],
)
def test_read_failure_categorized_without_leaking_token(code, expected):
    session = Mock()
    response = Mock()
    response.status_code = code
    response.json.return_value = {
        "ok": False,
        "error_code": code,
        "description": "secret-bot-token must never appear in errors",
    }
    session.get.return_value = response
    client = Telegram("secret-bot-token", "123", session=session)
    with pytest.raises(RuntimeError, match=f"^{expected}$") as exc:
        client.read("getUpdates", offset=4)
    assert "secret-bot-token" not in str(exc.value)


def test_read_success_preserves_updates():
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True, "result": [{"update_id": 17}]}
    session.get.return_value = response
    client = Telegram("test-token", "123", session=session)
    assert client.read("getUpdates", offset=17) == [{"update_id": 17}]


@pytest.mark.parametrize("payload", [[], None, "bad-response", {"ok": True, "result": {}}])
def test_getupdates_malformed_success_fails_closed(payload):
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = payload
    session.get.return_value = response
    client = Telegram("secret-bot-token", "123", session=session)
    with pytest.raises(RuntimeError) as exc:
        client.read("getUpdates", offset=17)
    assert str(exc.value) in ("telegram_read_rejected", "telegram_read_invalid_result")
    assert "secret-bot-token" not in str(exc.value)


@pytest.mark.parametrize("method", ["getMe", "getWebhookInfo"])
def test_telegram_metadata_rejects_non_object_result(method):
    session = Mock()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"ok": True, "result": []}
    session.get.return_value = response
    client = Telegram("secret-bot-token", "123", session=session)
    with pytest.raises(RuntimeError, match="^telegram_read_invalid_result$"):
        client.read(method)
