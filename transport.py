"""Confirmed Telegram delivery, explicit ambiguity handling, secret-free logs."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
import time

import requests
from market import DataError

LOG = logging.getLogger("laith")


def redact(text, secrets=()):
    value = str(text)
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)(apikey|api_key|token|password)=([^&\s]+)", r"\1=[REDACTED]", value)
    return re.sub(r"\b\d{7,12}:[A-Za-z0-9_-]{20,}\b", "[REDACTED]", value)


class SecretFilter(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = secrets

    def filter(self, record):
        record.msg = redact(record.getMessage(), self.secrets)
        record.args = ()
        # Only categorical errors are logged. Tracebacks can contain secret request URLs.
        record.exc_info = None
        record.exc_text = None
        return True


@dataclass
class Delivery:
    status: str
    message_id: int | None = None
    error: str | None = None
    retry_after: int = 0


class Telegram:
    def __init__(self, token, chat_id, session=None):
        self.base = "https://api.telegram.org/bot" + token
        self.chat_id = str(chat_id)
        self.session = session or requests.Session()

    def read(self, method, **params):
        if method not in ("getMe", "getWebhookInfo", "getUpdates"):
            raise ValueError("unsupported_read_method")
        try:
            response = self.session.get(self.base + "/" + method, params=params, timeout=(5, 15))
            data = response.json()
            if response.status_code != 200 or data.get("ok") is not True:
                raise RuntimeError("telegram_read_rejected")
            return data["result"]
        except (requests.RequestException, ValueError, KeyError, TypeError):
            raise RuntimeError("telegram_read_failed") from None

    def verify(self, expected_username):
        me = self.read("getMe")
        if me.get("username", "").lower() != expected_username.lstrip("@").lower():
            raise RuntimeError("telegram_bot_identity_mismatch")
        LOG.info("telegram_identity_verified username=%s", me["username"])
        return not self.read("getWebhookInfo").get("url")

    def send_to(self, chat_id, message):
        original=self.chat_id
        try:
            self.chat_id=str(chat_id)
            return self.send(message)
        finally:
            self.chat_id=original

    def send(self, message, reply_to_message_id=None):
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "HTML",
                   "link_preview_options": {"is_disabled": True}}
        if type(reply_to_message_id) is int and reply_to_message_id > 0:
            payload['reply_parameters'] = {'message_id': reply_to_message_id,
                                            'allow_sending_without_reply': True}
        try:
            response = self.session.post(self.base + "/sendMessage", json=payload, timeout=(5, 20))
        except requests.ConnectTimeout:
            return Delivery("retry", error="telegram_connect_timeout")
        except requests.RequestException:
            # A timeout/reset after writing may already have delivered the message.
            return Delivery("uncertain", error="telegram_delivery_unknown")
        try:
            data = response.json()
        except ValueError:
            return Delivery("uncertain", error="telegram_response_unknown")
        if not isinstance(data, dict):
            return Delivery("uncertain", error="telegram_response_unknown")
        if data.get("ok") is True:
            result = data.get("result", {})
            message_id = result.get("message_id")
            if not isinstance(message_id, int) or str(result.get("chat", {}).get("id")) != self.chat_id:
                return Delivery("uncertain", error="telegram_ack_invalid")
            return Delivery("sent", message_id=message_id)
        if data.get("ok") is not False:
            return Delivery("uncertain", error="telegram_ack_missing")
        code = data.get("error_code", response.status_code)
        if code == 429:
            delay = data.get("parameters", {}).get("retry_after", 30)
            delay = min(3600, max(1, int(delay))) if isinstance(delay, (int, float)) else 30
            return Delivery("retry", error="telegram_rate_limited", retry_after=delay)
        if isinstance(code, int) and code >= 500:
            return Delivery("retry", error="telegram_server_rejected")
        return Delivery("failed", error="telegram_request_rejected")


def dispatch(store, telegram, now=None, limit=5, market=None, only_kind=None):
    if callable(now):
        clock = now
    elif now is None:
        clock = time.time
    else:
        clock = lambda: float(now)
    for _ in range(limit):
        row = store.claim(clock(),only_kind=only_kind)
        if row is None:
            break
        if row['kind']=='emergency' and row.get('signal_id'):
            watch=store.trade(row['signal_id'])
            if not watch or watch['status'] not in ('active','uncertain_delivery'):
                store.finish(row['id'],'failed',clock(),error='signal_no_longer_active')
                continue
        if row['kind'] == 'entry':
            try:
                trade=store.trade(row['signal_id'])
                if market is None or not trade.get('quote_time'):
                    raise DataError('market_quote_unavailable')
                quote=market.quote(lambda: datetime.fromtimestamp(clock(),timezone.utc))
                checked_at=clock()
                if checked_at >= trade['entry_expires']:
                    raise DataError('market_quote_stale')
                if abs(quote['price']-trade['entry']) > trade['price_tolerance']:
                    raise DataError('market_price_moved')
                LOG.info('entry_presend_verified id=%s reference=%.2f quote=%.2f age=%.1f',
                         trade['id'],trade['entry'],quote['price'],checked_at-quote['time'])
            except DataError as exc:
                store.finish(row['id'],'failed',clock(),error=str(exc))
                store.set('last_error',str(exc))
                LOG.warning('entry_send_blocked id=%s reason=%s',row['id'],str(exc))
                continue
        reply_to = store.reply_target(row)
        outcome = (telegram.send(row["message"], reply_to_message_id=reply_to)
                   if reply_to is not None else telegram.send(row["message"]))
        store.finish(row["id"], outcome.status, clock(), outcome.message_id,
                     outcome.error, outcome.retry_after)
        LOG.info("delivery event=%s status=%s message_id=%s reply_to=%s error=%s", row["id"],
                 outcome.status, outcome.message_id, reply_to, outcome.error)
