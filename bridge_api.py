"""HTTP transport for the isolated Laith MT5 DEMO execution bridge.

This service is intentionally DEMO-only. It does not generate trading signals.
Approved upstream signals may be published to /publish; the MT5 EA polls /next.
Management actions for an already-open DEMO position use /manage.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import hashlib
import hmac
import json
import os
import re
import threading
import time

PORT = int(os.getenv("PORT", "8080"))
CLIENT_TOKEN = os.getenv("BRIDGE_CLIENT_TOKEN", "")
PUBLISH_TOKEN = os.getenv("BRIDGE_PUBLISH_TOKEN", "")
HMAC_SECRET = os.getenv("BRIDGE_HMAC_SECRET", "")
CONFIG_ENABLED = os.getenv("BRIDGE_ENABLED", "false").strip().lower() == "true"
MAX_AGE_SECONDS = 30
DELIVERY_LEASE_SECONDS = 5
MAX_PENDING = 1
FIXED_VOLUME = 0.01
STATE_FRESH_SECONDS = 10

if not CLIENT_TOKEN or not PUBLISH_TOKEN or not HMAC_SECRET:
    raise RuntimeError("bridge_tokens_required")

_lock = threading.Lock()
_items: dict[str, dict] = {}
_runtime_enabled = CONFIG_ENABLED
_client_state: dict | None = None
_key_re = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_reason_re = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _sign(text: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), text.encode(), hashlib.sha256).hexdigest()


def _command_text(item: dict) -> str:
    action = str(item.get("action", "OPEN")).upper()
    if action == "OPEN":
        return "|".join([
            "DEMO", item["key"], str(item["ts"]), item["symbol"],
            item["side"], item["volume"], item["sl"], item["tp"],
        ])
    return "|".join([
        "DEMO", "ACTION", item["key"], str(item["ts"]), item["symbol"],
        action, item.get("sl", "0.00000"), item.get("tp", "0.00000"),
    ])


def _wire_command(item: dict) -> str:
    text = _command_text(item)
    prefix = "CMD|" if str(item.get("action", "OPEN")).upper() == "OPEN" else "ACT|"
    return prefix + text + "|" + _sign(text)


def _authorized(handler, token_name: str, expected: str) -> bool:
    supplied = handler.headers.get(token_name, "")
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _pending_count(now: float | None = None) -> int:
    now = time.time() if now is None else now
    count = 0
    for item in _items.values():
        if item.get("ack") is not None:
            continue
        if now - item["ts"] <= MAX_AGE_SECONDS:
            count += 1
    return count


def _clean(now: float | None = None) -> None:
    now = time.time() if now is None else now
    for item in _items.values():
        if item.get("ack") is None and now - item["ts"] > MAX_AGE_SECONDS:
            item["ack"] = {"ok": False, "reason": "expired", "at": now}


def _state_age(now: float | None = None) -> float | None:
    now = time.time() if now is None else now
    if not _client_state:
        return None
    try:
        return max(0.0, now - float(_client_state.get("received_at", 0)))
    except (TypeError, ValueError):
        return None


def _state_is_fresh(now: float | None = None) -> bool:
    age = _state_age(now)
    return age is not None and age <= STATE_FRESH_SECONDS


def _validate_publish(data: dict) -> tuple[bool, str]:
    if not _runtime_enabled:
        return False, "kill_switch"
    if str(data.get("mode", "")).upper() != "DEMO":
        return False, "demo_only"
    key = str(data.get("key", ""))
    if not _key_re.fullmatch(key):
        return False, "invalid_key"
    symbol = str(data.get("symbol", "XAUUSD")).upper()
    if "XAUUSD" not in symbol:
        return False, "gold_only"
    side = str(data.get("side", "")).upper()
    if side not in ("BUY", "SELL"):
        return False, "invalid_side"
    if _truthy(data.get("forced", True)):
        return False, "forced_bias_blocked"
    try:
        volume = float(data.get("volume", 0))
        sl = float(data.get("sl"))
        tp = float(data.get("tp"))
    except (TypeError, ValueError):
        return False, "invalid_numbers"
    if abs(volume - FIXED_VOLUME) > 1e-9:
        return False, "volume_must_be_0_01"
    if sl <= 0 or tp <= 0:
        return False, "sl_tp_required"
    checks = data.get("checks", {})
    selected = checks.get(side) if isinstance(checks, dict) else None
    if not isinstance(selected, list) or len(selected) != 7:
        return False, "seven_checks_required"
    if sum(bool(x) for x in selected) < 6:
        return False, "strict_conditions_not_met"
    return True, "approved"


def _validate_manage(data: dict) -> tuple[bool, str]:
    if not _runtime_enabled:
        return False, "kill_switch"
    if str(data.get("mode", "")).upper() != "DEMO":
        return False, "demo_only"
    key = str(data.get("key", ""))
    if not _key_re.fullmatch(key):
        return False, "invalid_key"
    symbol = str(data.get("symbol", "XAUUSD")).upper()
    if "XAUUSD" not in symbol:
        return False, "gold_only"
    action = str(data.get("action", "")).upper()
    if action not in ("MODIFY", "CLOSE"):
        return False, "invalid_action"
    reason = str(data.get("reason", "")).strip()
    if not _reason_re.fullmatch(reason):
        return False, "reason_required"
    if action == "MODIFY":
        try:
            sl = float(data.get("sl"))
            tp = float(data.get("tp"))
        except (TypeError, ValueError):
            return False, "invalid_numbers"
        if sl <= 0 or tp <= 0:
            return False, "sl_tp_required"
    return True, "approved"


class Handler(BaseHTTPRequestHandler):
    server_version = "LaithDemoBridge/1.1"

    def log_message(self, fmt, *args):
        print("bridge_http", self.address_string(), fmt % args, flush=True)

    def _send(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8"):
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload, separators=(",", ":")), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            value = json.loads(raw.decode())
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = parse_qs(parsed.query)

        if path == "/health":
            with _lock:
                _clean()
                age = _state_age()
                payload = {
                    "ok": True,
                    "mode": "DEMO",
                    "enabled": bool(_runtime_enabled),
                    "pending": _pending_count(),
                    "max_age_seconds": MAX_AGE_SECONDS,
                    "fixed_volume": FIXED_VOLUME,
                    "client_state_fresh": bool(_state_is_fresh()),
                    "client_last_seen_age": round(age, 2) if age is not None else None,
                    "position_open": bool((_client_state or {}).get("position_open")),
                    "position_owned": bool((_client_state or {}).get("position_owned")),
                    "position_risk_usd": (_client_state or {}).get("position_risk_usd"),
                    "realized_bridge_profit_usd": (_client_state or {}).get("realized_bridge_profit_usd"),
                    "profit_risk_budget_usd": (_client_state or {}).get("profit_risk_budget_usd"),
                    "effective_risk_budget_usd": (_client_state or {}).get("effective_risk_budget_usd"),
                    "commissioning_used": (_client_state or {}).get("commissioning_used"),
                    "commissioning_remaining": (_client_state or {}).get("commissioning_remaining"),
                }
            return self._json(200, payload)

        if path == "/next":
            if not _authorized(self, "X-Bridge-Token", CLIENT_TOKEN):
                return self._send(401, "UNAUTHORIZED")
            with _lock:
                _clean()
                if not _runtime_enabled:
                    return self._send(423, "KILL_SWITCH")
                now = time.time()
                for item in _items.values():
                    if item.get("ack") is not None:
                        continue
                    if now - item["ts"] > MAX_AGE_SECONDS:
                        continue
                    delivered_at = item.get("delivered_at")
                    if delivered_at is not None and now - delivered_at < DELIVERY_LEASE_SECONDS:
                        continue
                    item["delivered_at"] = now
                    return self._send(200, _wire_command(item))
            return self._send(200, "NONE")

        if path == "/verify":
            if not _authorized(self, "X-Bridge-Token", CLIENT_TOKEN):
                return self._send(401, "UNAUTHORIZED")
            fields = {k: (v[0] if v else "") for k, v in q.items()}
            text = "|".join([
                "DEMO", fields.get("key", ""), fields.get("ts", ""),
                fields.get("symbol", ""), fields.get("side", ""),
                fields.get("volume", ""), fields.get("sl", ""), fields.get("tp", ""),
            ])
            sig = fields.get("sig", "")
            try:
                ts = int(fields.get("ts", "0"))
            except ValueError:
                return self._send(400, "BAD_TIMESTAMP")
            if abs(time.time() - ts) > MAX_AGE_SECONDS:
                return self._send(409, "STALE")
            if not hmac.compare_digest(_sign(text), sig):
                return self._send(403, "BAD_SIGNATURE")
            with _lock:
                item = _items.get(fields.get("key", ""))
                if item is None or item.get("ack") is not None:
                    return self._send(404, "UNKNOWN_OR_ACKED")
                if str(item.get("action", "OPEN")).upper() != "OPEN":
                    return self._send(409, "WRONG_ACTION_TYPE")
                if _command_text(item) != text:
                    return self._send(409, "COMMAND_MISMATCH")
                if not _runtime_enabled:
                    return self._send(423, "KILL_SWITCH")
            return self._send(200, "OK")

        if path == "/verify-action":
            if not _authorized(self, "X-Bridge-Token", CLIENT_TOKEN):
                return self._send(401, "UNAUTHORIZED")
            fields = {k: (v[0] if v else "") for k, v in q.items()}
            text = "|".join([
                "DEMO", "ACTION", fields.get("key", ""), fields.get("ts", ""),
                fields.get("symbol", ""), fields.get("action", ""),
                fields.get("sl", ""), fields.get("tp", ""),
            ])
            sig = fields.get("sig", "")
            try:
                ts = int(fields.get("ts", "0"))
            except ValueError:
                return self._send(400, "BAD_TIMESTAMP")
            if abs(time.time() - ts) > MAX_AGE_SECONDS:
                return self._send(409, "STALE")
            if not hmac.compare_digest(_sign(text), sig):
                return self._send(403, "BAD_SIGNATURE")
            with _lock:
                item = _items.get(fields.get("key", ""))
                if item is None or item.get("ack") is not None:
                    return self._send(404, "UNKNOWN_OR_ACKED")
                if str(item.get("action", "OPEN")).upper() == "OPEN":
                    return self._send(409, "WRONG_ACTION_TYPE")
                if _command_text(item) != text:
                    return self._send(409, "COMMAND_MISMATCH")
                if not _runtime_enabled:
                    return self._send(423, "KILL_SWITCH")
            return self._send(200, "OK")

        return self._send(404, "NOT_FOUND")

    def do_POST(self):
        global _runtime_enabled, _client_state
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/publish":
            if not _authorized(self, "X-Publish-Token", PUBLISH_TOKEN):
                return self._json(401, {"ok": False, "reason": "unauthorized"})
            data = self._read_json()
            with _lock:
                _clean()
                ok, reason = _validate_publish(data)
                if not ok:
                    return self._json(400, {"ok": False, "reason": reason})
                key = str(data["key"])
                if key in _items:
                    return self._json(409, {"ok": False, "reason": "duplicate_order", "key": key})
                if _pending_count() >= MAX_PENDING:
                    return self._json(409, {"ok": False, "reason": "position_or_command_limit"})
                item = {
                    "action": "OPEN",
                    "key": key,
                    "ts": int(time.time()),
                    "symbol": "XAUUSD",
                    "side": str(data["side"]).upper(),
                    "volume": f"{FIXED_VOLUME:.2f}",
                    "sl": f"{float(data['sl']):.5f}",
                    "tp": f"{float(data['tp']):.5f}",
                    "ack": None,
                    "delivered_at": None,
                }
                _items[key] = item
                return self._json(201, {"ok": True, "key": key, "mode": "DEMO", "action": "OPEN"})

        if path == "/manage":
            if not _authorized(self, "X-Publish-Token", PUBLISH_TOKEN):
                return self._json(401, {"ok": False, "reason": "unauthorized"})
            data = self._read_json()
            with _lock:
                _clean()
                ok, reason = _validate_manage(data)
                if not ok:
                    return self._json(400, {"ok": False, "reason": reason})
                if not _state_is_fresh():
                    return self._json(409, {"ok": False, "reason": "client_state_stale"})
                if not bool((_client_state or {}).get("position_open")):
                    return self._json(409, {"ok": False, "reason": "no_open_position"})
                if not bool((_client_state or {}).get("position_owned")):
                    return self._json(409, {"ok": False, "reason": "position_not_owned_by_bridge"})
                key = str(data["key"])
                if key in _items:
                    return self._json(409, {"ok": False, "reason": "duplicate_order", "key": key})
                if _pending_count() >= MAX_PENDING:
                    return self._json(409, {"ok": False, "reason": "position_or_command_limit"})
                action = str(data["action"]).upper()
                item = {
                    "action": action,
                    "key": key,
                    "ts": int(time.time()),
                    "symbol": "XAUUSD",
                    "sl": f"{float(data.get('sl', 0)):.5f}",
                    "tp": f"{float(data.get('tp', 0)):.5f}",
                    "reason": str(data.get("reason", "")),
                    "ack": None,
                    "delivered_at": None,
                }
                _items[key] = item
                return self._json(201, {"ok": True, "key": key, "mode": "DEMO", "action": action})

        if path == "/state":
            if not _authorized(self, "X-Bridge-Token", CLIENT_TOKEN):
                return self._json(401, {"ok": False, "reason": "unauthorized"})
            data = self._read_json()
            if str(data.get("mode", "")).upper() != "DEMO":
                return self._json(400, {"ok": False, "reason": "demo_only"})
            symbol = str(data.get("symbol", "")).upper()
            if "XAUUSD" not in symbol:
                return self._json(400, {"ok": False, "reason": "gold_only"})
            clean_state = {
                "mode": "DEMO",
                "symbol": symbol[:32],
                "position_open": bool(data.get("position_open")),
                "position_owned": bool(data.get("position_owned")),
                "ticket": str(data.get("ticket", ""))[:40],
                "side": str(data.get("side", ""))[:8],
                "volume": str(data.get("volume", ""))[:24],
                "open_price": str(data.get("open_price", ""))[:32],
                "sl": str(data.get("sl", ""))[:32],
                "tp": str(data.get("tp", ""))[:32],
                "price": str(data.get("price", ""))[:32],
                "profit": str(data.get("profit", ""))[:32],
                "magic": str(data.get("magic", ""))[:32],
                "position_risk_usd": str(data.get("position_risk_usd", ""))[:32],
                "realized_bridge_profit_usd": str(data.get("realized_bridge_profit_usd", ""))[:32],
                "profit_risk_budget_usd": str(data.get("profit_risk_budget_usd", ""))[:32],
                "effective_risk_budget_usd": str(data.get("effective_risk_budget_usd", ""))[:32],
                "commissioning_used": str(data.get("commissioning_used", ""))[:16],
                "commissioning_remaining": str(data.get("commissioning_remaining", ""))[:16],
                "received_at": time.time(),
            }
            with _lock:
                _client_state = clean_state
            return self._json(200, {"ok": True})

        if path == "/ack":
            if not _authorized(self, "X-Bridge-Token", CLIENT_TOKEN):
                return self._json(401, {"ok": False, "reason": "unauthorized"})
            data = self._read_json()
            key = str(data.get("key", ""))
            with _lock:
                item = _items.get(key)
                if item is None:
                    return self._json(404, {"ok": False, "reason": "unknown_order"})
                if item.get("ack") is not None:
                    return self._json(409, {"ok": False, "reason": "already_acknowledged"})
                item["ack"] = {
                    "ok": bool(data.get("ok")),
                    "reason": str(data.get("reason", ""))[:120],
                    "ticket": str(data.get("ticket", ""))[:40],
                    "at": time.time(),
                }
            return self._json(200, {"ok": True, "key": key})

        if path == "/kill":
            if not _authorized(self, "X-Publish-Token", PUBLISH_TOKEN):
                return self._json(401, {"ok": False, "reason": "unauthorized"})
            with _lock:
                _runtime_enabled = False
            return self._json(200, {"ok": True, "enabled": False, "mode": "DEMO"})

        if path == "/resume":
            if not _authorized(self, "X-Publish-Token", PUBLISH_TOKEN):
                return self._json(401, {"ok": False, "reason": "unauthorized"})
            if not CONFIG_ENABLED:
                return self._json(409, {"ok": False, "reason": "config_disabled"})
            with _lock:
                _runtime_enabled = True
            return self._json(200, {"ok": True, "enabled": True, "mode": "DEMO"})

        return self._send(404, "NOT_FOUND")


if __name__ == "__main__":
    print(f"LAITH_BRIDGE_API_START mode=DEMO enabled={CONFIG_ENABLED} port={PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
