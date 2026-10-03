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
EFFECTIVE_RISK_BUDGET_USD = float(os.getenv("REAL_EFFECTIVE_RISK_BUDGET_USD", "3") or 3)
STRONG_RISK_BUDGET_USD = float(os.getenv("REAL_STRONG_RISK_BUDGET_USD", "15") or 15)
MAX_AGE_SECONDS = 30
STATE_FRESH_SECONDS = 10
MARKET_FRESH_SECONDS = 20
MARKET_SOURCE_FRESH_SECONDS = 900
MARKET_TICK_FRESH_SECONDS = 45
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
# Restart latch: a REAL bridge process always starts in fail-closed emergency
# state. A crash/redeploy can therefore never silently forget a prior stop.
# This candidate intentionally contains no network endpoint that clears it.
_restart_latched = True
_emergency_stop = True
_key_re = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _configured() -> bool:
    return bool(CLIENT_TOKEN and PUBLISH_TOKEN and HMAC_SECRET and FIXED_VOLUME > 0)


def _ready() -> bool:
    s_age = _state_age()
    m_age = _market_age()
    p_age = _client_poll_age()
    return bool(
        REAL_ARMED and EXECUTION_ENABLED and _configured() and not _emergency_stop
        and s_age is not None and s_age <= STATE_FRESH_SECONDS
        and m_age is not None and m_age <= MARKET_FRESH_SECONDS
        and p_age is not None and p_age <= 10
    )


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


def _market_source_age(payload=None, now=None):
    payload = _market_state if payload is None else payload
    if not payload:
        return None
    now = time.time() if now is None else now
    try:
        ts = float(payload.get("source_timestamp", 0))
        if ts <= 0:
            return None
        return max(0.0, now - ts)
    except (TypeError, ValueError):
        return None


def _market_tick_age(payload=None, now=None):
    payload = _market_state if payload is None else payload
    if not payload:
        return None
    now = time.time() if now is None else now
    try:
        ts = float(payload.get("tick_timestamp", 0))
        if ts <= 0:
            return None
        return max(0.0, now - ts)
    except (TypeError, ValueError):
        return None


def _validate_market_payload(data: dict, now=None):
    feeds = {k: data.get(k) for k in ("m5", "m15", "h4")}
    if not all(isinstance(v, list) and len(v) >= 30 for v in feeds.values()):
        return False, "market_rows_required"
    if str(data.get("h4_source") or "") != "MT5_NATIVE_TIMEFRAME_H4":
        return False, "native_h4_required"
    if str(data.get("source_clock") or "") != "UTC_EPOCH":
        return False, "utc_source_clock_required"
    tick_age = _market_tick_age(data, now)
    if tick_age is None:
        return False, "market_tick_timestamp_required"
    if tick_age > MARKET_TICK_FRESH_SECONDS:
        return False, "market_tick_stale"
    source_age = _market_source_age(data, now)
    if source_age is None:
        return False, "market_source_timestamp_required"
    if source_age > MARKET_SOURCE_FRESH_SECONDS:
        return False, "market_source_stale"
    return True, "approved"


def _client_poll_age(now=None):
    if _client_last_poll is None:
        return None
    now = time.time() if now is None else now
    return max(0.0, now - float(_client_last_poll))


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


def _readiness_blockers(now=None):
    now = time.time() if now is None else now
    blockers = []
    s_age = _state_age(now)
    m_age = _market_age(now)
    source_age = _market_source_age(_market_state, now)
    tick_age = _market_tick_age(_market_state, now)
    if not CLIENT_TOKEN or not PUBLISH_TOKEN or not HMAC_SECRET:
        blockers.append("auth_incomplete")
    if FIXED_VOLUME <= 0:
        blockers.append("risk_unset")
    if not REAL_ARMED:
        blockers.append("not_armed")
    if not EXECUTION_ENABLED:
        blockers.append("execution_disabled")
    if _emergency_stop:
        blockers.append("emergency_stop")
    if s_age is None or s_age > STATE_FRESH_SECONDS:
        blockers.append("mt5_state_stale")
    p_age = _client_poll_age(now)
    if p_age is None or p_age > 10:
        blockers.append("executor_not_connected")
    if (
        m_age is None or m_age > MARKET_FRESH_SECONDS
        or source_age is None or source_age > MARKET_SOURCE_FRESH_SECONDS
        or tick_age is None or tick_age > MARKET_TICK_FRESH_SECONDS
    ):
        blockers.append("market_closed_or_stale")
    return blockers


def _status():
    now = time.time()
    s_age = _state_age(now)
    m_age = _market_age(now)
    source_age = _market_source_age(_market_state, now)
    tick_age = _market_tick_age(_market_state, now)
    poll_age = _client_poll_age(now)
    state = _client_state or {}
    return {
        "ok": True,
        "mode": "REAL",
        "armed": REAL_ARMED,
        "execution_enabled": EXECUTION_ENABLED,
        "emergency_stop": bool(_emergency_stop),
        "restart_latched": bool(_restart_latched),
        "configured": _configured(),
        "auth_configured": bool(CLIENT_TOKEN and PUBLISH_TOKEN and HMAC_SECRET),
        "client_auth_configured": bool(CLIENT_TOKEN),
        "publish_auth_configured": bool(PUBLISH_TOKEN),
        "hmac_configured": bool(HMAC_SECRET),
        "ready": _ready(),
        "readiness_blockers": _readiness_blockers(now),
        "preflight_ok": len(_readiness_blockers(now)) == 0,
        "fixed_volume_configured": FIXED_VOLUME > 0,
        "fixed_volume": FIXED_VOLUME,
        "effective_risk_budget_usd": EFFECTIVE_RISK_BUDGET_USD,
        "strong_risk_budget_usd": STRONG_RISK_BUDGET_USD,
        "position_risk_usd": state.get("position_risk_usd", 0),
        "client_state_fresh": s_age is not None and s_age <= STATE_FRESH_SECONDS,
        "client_state_age": s_age,
        "executor_poll_fresh": poll_age is not None and poll_age <= 10,
        "executor_poll_age": poll_age,
        "market_fresh": (
            m_age is not None and m_age <= MARKET_FRESH_SECONDS
            and source_age is not None and source_age <= MARKET_SOURCE_FRESH_SECONDS
            and tick_age is not None and tick_age <= MARKET_TICK_FRESH_SECONDS
        ),
        "market_age": m_age,
        "market_source_age": source_age,
        "market_tick_age": tick_age,
        "pending": _pending_count(now),
        "price": state.get("price", 0),
        "position_open": bool(state.get("position_open")),
        "position_owned": bool(state.get("position_owned")),
        "position_risk_usd": state.get("position_risk_usd", 0),
        "total_position_risk_usd": state.get("total_position_risk_usd", 0),
        "main_position_risk_usd": state.get("main_position_risk_usd"),
        "sniper_position_risk_usd": state.get("sniper_position_risk_usd"),
        "unknown_position_risk_usd": state.get("unknown_position_risk_usd", 0),
        "effective_risk_budget_usd": state.get("effective_risk_budget_usd"),
        "strong_risk_budget_usd": state.get("strong_risk_budget_usd"),
        "profit_risk_budget_usd": state.get("profit_risk_budget_usd"),
        "owned_position_count": state.get("owned_position_count", 0),
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
    if _emergency_stop:
        return False, "real_emergency_stop"
    s_age = _state_age()
    if s_age is None or s_age > STATE_FRESH_SECONDS:
        return False, "real_state_stale"
    m_age = _market_age()
    if m_age is None or m_age > MARKET_FRESH_SECONDS:
        return False, "real_market_stale"
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
                payload.update({k: _market_state.get(k) for k in ("m5", "m15", "h1", "h4")})
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
        global _client_state, _market_state, _emergency_stop
        path = urlparse(self.path).path
        if path == "/emergency-stop":
            if not ALLOWED_ORIGIN or self.headers.get("Origin", "") != ALLOWED_ORIGIN:
                return _json(self, 401, {"ok": False, "reason": "trusted_app_origin_required"})
            with _lock:
                _emergency_stop = True
                now = time.time()
                for item in _items.values():
                    if item.get("ack") is None:
                        item["ack"] = {"ok": False, "reason": "emergency_stop", "at": now}
            return _json(self, 200, _status())

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
            ok, reason = _validate_market_payload(data)
            if not ok:
                return _json(self, 409 if reason == "market_source_stale" else 400, {"ok": False, "reason": reason})
            _market_state = {
                "m5": data.get("m5"),
                "m15": data.get("m15"),
                "h1": data.get("h1"),
                "h4": data.get("h4"),
                "h4_source": data.get("h4_source"),
                "source_clock": data.get("source_clock"),
                "source_timestamp": data.get("source_timestamp"),
                "tick_timestamp": data.get("tick_timestamp"),
                "received_at": time.time(),
            }
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
        f"emergency_stop={s['emergency_stop']} configured={s['configured']} ready={s['ready']} "
        f"fixed_volume_configured={s['fixed_volume_configured']}",
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
