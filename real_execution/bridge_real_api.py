"""Fail-closed HTTP bridge for a future REAL MT5 executor.

The service is deliberately safe by default:
- REAL_BRIDGE_ARMED=false
- REAL_EXECUTION_ENABLED=false
- REAL_FIXED_VOLUME=0
- missing auth secrets are allowed only while disabled
No trade command can be delivered unless every readiness gate is explicitly configured.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import hashlib
import hmac
import json
import os
import re
import threading
import time

PORT = int(os.getenv("PORT", "8080"))
CLIENT_TOKEN = os.getenv("REAL_BRIDGE_CLIENT_TOKEN", "").strip()
PUBLISH_TOKEN = os.getenv("REAL_BRIDGE_PUBLISH_TOKEN", "").strip()
HMAC_SECRET = os.getenv("REAL_BRIDGE_HMAC_SECRET", "").strip()
REAL_ARMED = os.getenv("REAL_BRIDGE_ARMED", "false").strip().lower() == "true"
EXECUTION_ENABLED = os.getenv("REAL_EXECUTION_ENABLED", "false").strip().lower() == "true"
FIXED_VOLUME = float(os.getenv("REAL_FIXED_VOLUME", "0") or 0)
MAX_AGE_SECONDS = 30
STATE_FRESH_SECONDS = 10
MARKET_FRESH_SECONDS = 20
MAX_PENDING = 2
ALLOWED_ORIGIN = os.getenv(
    "REAL_STATUS_ALLOWED_ORIGIN",
    "https://laith-app-production.up.railway.app",
).strip()

_lock = threading.Lock()
_items: dict[str, dict] = {}
_client_state: dict | None = None
_market_state: dict | None = None
_client_last_poll: float | None = None
_key_re = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _configured() -> bool:
    return bool(CLIENT_TOKEN and PUBLISH_TOKEN and HMAC_SECRET and FIXED_VOLUME > 0)


def _ready() -> bool:
    return bool(REAL_ARMED and EXECUTION_ENABLED and _configured())


def _sign(text: str) -> str:
    return hmac.new(HMAC_SECRET.encode(), text.encode(), hashlib.sha256).hexdigest()


def _authorized(handler, header: str, expected: str) -> bool:
    supplied = handler.headers.get(header, "")
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _state_age(now=None):
    if not _client_state:
        return None
    now = time.time() if now is None else now
    try:
        return max(0.0, now - float(_client_state.get("received_at", 0)))
    except (TypeError, ValueError):
        return None


def _market_age(now=None):
    if not _market_state:
        return None
    now = time.time() if now is None else now
    try:
        return max(0.0, now - float(_market_state.get("received_at", 0)))
    except (TypeError, ValueError):
        return None


def _pending_count(now=None):
    now = time.time() if now is None else now
    count = 0
    for item in _items.values():
        if item.get("ack") is not None:
            continue
        if now - item["ts"] <= MAX_AGE_SECONDS:
            count += 1
    return count


def _clean(now=None):
    now = time.time() if now is None else now
    for item in _items.values():
        if item.get("ack") is None and now - item["ts"] > MAX_AGE_SECONDS:
            item["ack"] = {"ok": False, "reason": "expired", "at": now}


def _status():
    now = time.time()
    s_age = _state_age(now)
    m_age = _market_age(now)
    state = _client_state or {}
    return {
        "ok": True,
        "mode": "REAL",
        "armed": REAL_ARMED,
        "execution_enabled": EXECUTION_ENABLED,
        "configured": _configured(),
        "ready": _ready(),
        "fixed_volume_configured": FIXED_VOLUME > 0,
        "client_state_fresh": s_age is not None and s_age <= STATE_FRESH_SECONDS,
        "client_state_age": s_age,
        "market_fresh": m_age is not None and m_age <= MARKET_FRESH_SECONDS,
        "market_age": m_age,
        "pending": _pending_count(now),
        "price": state.get("price", 0),
        "position_open": bool(state.get("position_open")),
        "position_owned": bool(state.get("position_owned")),
        "total_position_risk_usd": state.get("total_position_risk_usd", 0),
    }


def _validate_publish(data: dict):
    if not REAL_ARMED:
        return False, "real_not_armed"
    if not EXECUTION_ENABLED:
        return False, "real_execution_disabled"
    if not _configured():
        if FIXED_VOLUME <= 0:
            return False, "real_volume_not_configured"
        return False, "real_auth_not_configured"
    if str(data.get("mode", "")).upper() != "REAL":
        return False, "real_mode_required"
    key = str(data.get("key", ""))
    if not _key_re.fullmatch(key):
        return False, "invalid_key"
    symbol = str(data.get("symbol", "")).upper()
    if "XAUUSD" not in symbol:
        return False, "gold_only"
    side = str(data.get("side", "")).upper()
    if side not in ("BUY", "SELL"):
        return False, "invalid_side"
    trade_mode = str(data.get("trade_mode", "")).upper()
    if trade_mode not in ("MAIN", "SNIPER"):
        return False, "invalid_trade_mode"
    if bool(data.get("forced", True)):
        return False, "forced_bias_blocked"
    try:
        volume = float(data.get("volume", 0))
        sl = float(data.get("sl", 0))
        tp = float(data.get("tp", 0))
    except (TypeError, ValueError):
        return False, "invalid_numbers"
    if abs(volume - FIXED_VOLUME) > 1e-9:
        return False, "volume_mismatch"
    if sl <= 0 or tp <= 0:
        return False, "sl_tp_required"
    checks = data.get("checks", {})
    selected = checks.get(side) if isinstance(checks, dict) else None
    if not isinstance(selected, list) or len(selected) != 7:
        return False, "seven_checks_required"
    minimum = 3 if trade_mode == "SNIPER" else 5
    if sum(bool(x) for x in selected) < minimum:
        return False, "conditions_not_met"
    if _pending_count() >= MAX_PENDING:
        return False, "pending_limit"
    return True, "approved"


def _command_text(item: dict) -> str:
    return "|".join([
        "REAL", item["key"], str(item["ts"]), item["symbol"],
        item["side"], item["volume"], item["sl"], item["tp"],
    ])


def _wire_command(item: dict) -> str:
    text = _command_text(item)
    return "CMD|" + text + "|" + _sign(text)


def _cors(handler):
    origin = handler.headers.get("Origin", "")
    if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN:
        handler.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        handler.send_header("Vary", "Origin")


def _json(handler, status, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    _cors(handler)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    try:
        size = int(handler.headers.get("Content-Length", "0") or 0)
        raw = handler.rfile.read(size) if size else b"{}"
        return json.loads(raw.decode() or "{}")
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "LaithRealBridge/1.0"

    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        global _client_last_poll
        path = urlparse(self.path).path
        if path in ("/", "/health", "/status"):
            return _json(self, 200, _status())
        if path == "/market":
            payload = {"ok": True}
            if _market_state:
                payload.update({k: _market_state.get(k) for k in ("m5", "m15", "h1")})
                payload["market_age"] = _market_age()
            return _json(self, 200, payload)
        if path == "/verify":
            if not _authorized(self, "X-Client-Token", CLIENT_TOKEN):
                return _json(self, 401, {"ok": False, "reason": "client_auth_required"})
            if not _ready():
                return _json(self, 423, {"ok": False, "reason": "real_bridge_locked"})
            from urllib.parse import parse_qs
            q = parse_qs(urlparse(self.path).query)
            def one(name):
                return (q.get(name) or [""])[0]
            text = "|".join([
                "REAL", one("key"), one("ts"), one("symbol"),
                one("side"), one("volume"), one("sl"), one("tp"),
            ])
            supplied = one("sig")
            if supplied and hmac.compare_digest(supplied, _sign(text)):
                body = b"OK"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return _json(self, 403, {"ok": False, "reason": "signature_invalid"})
        if path == "/next":
            if not _authorized(self, "X-Client-Token", CLIENT_TOKEN):
                return _json(self, 401, {"ok": False, "reason": "client_auth_required"})
            _client_last_poll = time.time()
            if not _ready():
                return _json(self, 423, {"ok": False, "reason": "real_bridge_locked"})
            with _lock:
                _clean()
                for item in _items.values():
                    if item.get("ack") is None:
                        body = _wire_command(item).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/plain")
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
            body = b"NONE"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return _json(self, 404, {"ok": False, "reason": "not_found"})

    def do_POST(self):
        global _client_state, _market_state
        path = urlparse(self.path).path
        data = _read_json(self)
        if data is None:
            return _json(self, 400, {"ok": False, "reason": "invalid_json"})

        if path in ("/state", "/market", "/ack"):
            if not _authorized(self, "X-Client-Token", CLIENT_TOKEN):
                return _json(self, 401, {"ok": False, "reason": "client_auth_required"})

        if path == "/state":
            data = dict(data)
            data["received_at"] = time.time()
            _client_state = data
            return _json(self, 200, {"ok": True})

        if path == "/market":
            feeds = {k: data.get(k) for k in ("m5", "m15", "h1")}
            if not all(isinstance(v, list) and len(v) >= 30 for v in feeds.values()):
                return _json(self, 400, {"ok": False, "reason": "market_rows_required"})
            _market_state = {**feeds, "received_at": time.time()}
            return _json(self, 200, {"ok": True})

        if path == "/publish":
            if not _authorized(self, "X-Publish-Token", PUBLISH_TOKEN):
                return _json(self, 401, {"ok": False, "reason": "publish_auth_required"})
            ok, reason = _validate_publish(data)
            if not ok:
                return _json(self, 423 if reason.startswith("real_") else 400, {"ok": False, "reason": reason})
            now = time.time()
            item = {
                "key": str(data["key"]),
                "ts": int(now),
                "symbol": str(data["symbol"]),
                "side": str(data["side"]).upper(),
                "volume": f"{float(data['volume']):.2f}",
                "sl": f"{float(data['sl']):.5f}",
                "tp": f"{float(data['tp']):.5f}",
                "ack": None,
            }
            with _lock:
                _clean(now)
                if item["key"] in _items:
                    return _json(self, 409, {"ok": False, "reason": "duplicate_key"})
                _items[item["key"]] = item
            return _json(self, 201, {"ok": True, "key": item["key"]})

        if path == "/ack":
            key = str(data.get("key", ""))
            with _lock:
                item = _items.get(key)
                if not item:
                    return _json(self, 404, {"ok": False, "reason": "unknown_key"})
                item["ack"] = {
                    "ok": bool(data.get("ok")),
                    "reason": str(data.get("reason", ""))[:100],
                    "ticket": str(data.get("ticket", ""))[:40],
                    "at": time.time(),
                }
            return _json(self, 200, {"ok": True})

        return _json(self, 404, {"ok": False, "reason": "not_found"})


if __name__ == "__main__":
    s = _status()
    print(
        "REAL_BRIDGE_START "
        f"armed={s['armed']} execution_enabled={s['execution_enabled']} "
        f"configured={s['configured']} ready={s['ready']} "
        f"fixed_volume_configured={s['fixed_volume_configured']}",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
