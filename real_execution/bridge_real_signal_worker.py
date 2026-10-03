"""REAL analysis/signal service scaffold.

Fail-closed defaults:
- analysis preview disabled
- REAL signal disabled
- volume and hourly cap unset
- live handoff permanently disabled in this build
The service may calculate a read-only candidate after preview is explicitly
enabled, but it cannot publish an order in this build.
"""
from __future__ import annotations

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from technical_confirmation import analyze as analyze_technical

REAL_ANALYSIS_PREVIEW_ENABLED = os.getenv("REAL_ANALYSIS_PREVIEW_ENABLED", "false").strip().lower() == "true"
REAL_SIGNAL_ENABLED = os.getenv("REAL_SIGNAL_ENABLED", "false").strip().lower() == "true"
BRIDGE_URL = os.getenv("REAL_BRIDGE_URL", "").strip().rstrip("/")
PUBLISH_TOKEN = os.getenv("REAL_BRIDGE_PUBLISH_TOKEN", "").strip()
VOLUME = float(os.getenv("REAL_VOLUME", "0") or 0)
POLL_SECONDS = int(os.getenv("REAL_POLL_SECONDS", "30"))
MAX_PUBLISH_PER_HOUR = int(os.getenv("REAL_MAX_PUBLISH_PER_HOUR", "0") or 0)
STATUS_PORT = int(os.getenv("PORT", "8080"))
ALLOWED_ORIGIN = os.getenv(
    "REAL_STATUS_ALLOWED_ORIGIN",
    "https://laith-app-production.up.railway.app",
).strip()

_preview_enabled = REAL_ANALYSIS_PREVIEW_ENABLED
_latest_preview = {
    "available": False,
    "reason": "preview_disabled",
    "updated_at": 0.0,
}


def _json_request(url, method="GET", payload=None, headers=None, timeout=8):
    data = None
    hs = {"Accept": "application/json"}
    if headers:
        hs.update(headers)
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        hs["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=hs)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode()
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {"detail": raw[:200]}
        return exc.code, body


def config_reason():
    if not REAL_SIGNAL_ENABLED:
        return "real_signal_disabled"
    if not BRIDGE_URL or not PUBLISH_TOKEN:
        return "real_signal_auth_not_configured"
    if VOLUME <= 0:
        return "real_signal_volume_not_configured"
    if MAX_PUBLISH_PER_HOUR <= 0:
        return "real_signal_hourly_cap_not_configured"
    return None


def analysis_reason():
    if not _preview_enabled:
        return "preview_disabled"
    if not BRIDGE_URL:
        return "preview_bridge_not_configured"
    return None


def _parse_dt(value):
    return datetime.fromisoformat(str(value).replace(".", "-", 2).replace("Z", "+00:00"))


def normalize_rows(values):
    if not isinstance(values, list) or len(values) < 30:
        raise ValueError("not_enough_market_rows")
    rows = []
    for item in values:
        if not isinstance(item, dict) or not item.get("datetime"):
            continue
        rows.append({
            "datetime": str(item["datetime"]).replace(".", "-", 2),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "tick_volume": float(item.get("tick_volume") or 0),
        })
    if len(rows) < 30:
        raise ValueError("not_enough_market_rows")
    rows.sort(key=lambda row: _parse_dt(row["datetime"]))
    # MT5 relay includes the active candle as the newest item.
    return rows[:-1]


def _ema(values, period):
    alpha = 2.0 / (period + 1.0)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1.0 - alpha) * out[-1])
    return out


def _rsi(closes, period=14):
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for a, b in zip(closes[-period-1:-1], closes[-period:]):
        ch = b - a
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    ag = sum(gains) / period
    al = sum(losses) / period
    if al <= 1e-12:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _aggregate_h4(h1_rows):
    buckets = {}
    for row in h1_rows:
        dt = _parse_dt(row["datetime"])
        key = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
        k = key.isoformat(sep=" ")
        b = buckets.get(k)
        if b is None:
            buckets[k] = {
                "datetime": k,
                "open": row["open"], "high": row["high"], "low": row["low"],
                "close": row["close"], "tick_volume": row.get("tick_volume", 0),
            }
        else:
            b["high"] = max(b["high"], row["high"])
            b["low"] = min(b["low"], row["low"])
            b["close"] = row["close"]
            b["tick_volume"] += row.get("tick_volume", 0)
    return [buckets[k] for k in sorted(buckets)]


def _trend(rows):
    closes = [r["close"] for r in rows]
    if len(closes) < 22:
        return "NEUTRAL"
    e8 = _ema(closes, 8)
    e21 = _ema(closes, 21)
    slope = e21[-1] - e21[-4]
    if e8[-1] > e21[-1] and slope > 0:
        return "UP"
    if e8[-1] < e21[-1] and slope < 0:
        return "DOWN"
    return "NEUTRAL"


def fetch_market():
    status, payload = _json_request(f"{BRIDGE_URL}/market")
    if status != 200 or payload.get("ok") is not True:
        raise RuntimeError(f"market_http_{status}")
    age = payload.get("market_age")
    if age is None or float(age) > 20:
        raise RuntimeError("market_stale")
    feeds = {
        "m5": payload.get("m5"),
        "m15": payload.get("m15"),
        "h1": payload.get("h1"),
    }
    if not all(isinstance(v, list) and len(v) >= 30 for v in feeds.values()):
        raise RuntimeError("market_rows_missing")
    return feeds


def compute_preview(feeds):
    m5 = normalize_rows(feeds["m5"])
    m15 = normalize_rows(feeds["m15"])
    h1 = normalize_rows(feeds["h1"])
    h4 = _aggregate_h4(h1)
    h4_bias = _trend(h4)
    h1_bias = _trend(h1)

    m15_closes = [r["close"] for r in m15]
    m5_closes = [r["close"] for r in m5]
    e8 = _ema(m15_closes, 8)
    e21 = _ema(m15_closes, 21)
    rsi = _rsi(m15_closes)
    momentum = m15_closes[-1] - m15_closes[-4]
    tech = analyze_technical(m15)

    m15_up = e8[-1] > e21[-1] and momentum > 0 and rsi >= 52
    m15_down = e8[-1] < e21[-1] and momentum < 0 and rsi <= 48
    m5_up = m5_closes[-1] > m5_closes[-2] > m5_closes[-3]
    m5_down = m5_closes[-1] < m5_closes[-2] < m5_closes[-3]

    bull = int(h4_bias == "UP") + int(h1_bias == "UP") + int(m15_up) + int(m5_up)
    bear = int(h4_bias == "DOWN") + int(h1_bias == "DOWN") + int(m15_down) + int(m5_down)
    bull += int(int(tech.get("bull_score") or 0) > int(tech.get("bear_score") or 0))
    bear += int(int(tech.get("bear_score") or 0) > int(tech.get("bull_score") or 0))

    side = "WAIT"
    reason = "alignment_incomplete"
    if bull >= 4 and bull > bear and h4_bias != "DOWN" and h1_bias != "DOWN":
        side = "BUY"
        reason = "multitimeframe_buy_preview"
    elif bear >= 4 and bear > bull and h4_bias != "UP" and h1_bias != "UP":
        side = "SELL"
        reason = "multitimeframe_sell_preview"

    return {
        "available": True,
        "side": side,
        "reason": reason,
        "score": max(bull, bear),
        "h4": h4_bias,
        "h1": h1_bias,
        "m15_rsi": round(rsi, 1),
        "m15_momentum": round(momentum, 3),
        "bar": m15[-1]["datetime"],
        "reference_close": m15[-1]["close"],
        "live_handoff_enabled": False,
        "updated_at": time.time(),
    }


def bridge_health():
    status, payload = _json_request(f"{BRIDGE_URL}/health")
    if status != 200:
        raise RuntimeError(f"bridge_health_http_{status}")
    return payload


def status_payload():
    return {
        "ok": True,
        "mode": "REAL",
        "analysis_preview_enabled": _preview_enabled,
        "enabled": REAL_SIGNAL_ENABLED,
        "volume_configured": VOLUME > 0,
        "hourly_cap_configured": MAX_PUBLISH_PER_HOUR > 0,
        "bridge_configured": bool(BRIDGE_URL and PUBLISH_TOKEN),
        "analysis_reason": analysis_reason(),
        "config_reason": config_reason(),
        "live_handoff_enabled": False,
        "preview": _latest_preview,
    }


def _cors(handler):
    origin = handler.headers.get("Origin", "")
    if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN:
        handler.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        handler.send_header("Vary", "Origin")


class StatusHandler(BaseHTTPRequestHandler):
    server_version = "LaithRealSignalStatus/1.1"

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
        if self.path not in ("/", "/health", "/status"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(status_payload(), separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        _cors(self)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        global _preview_enabled, _latest_preview
        if self.path != "/preview":
            self.send_response(404)
            self.end_headers()
            return
        if not ALLOWED_ORIGIN or self.headers.get("Origin", "") != ALLOWED_ORIGIN:
            body = b'{"ok":false,"reason":"trusted_app_origin_required"}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            size = int(self.headers.get("Content-Length", "0") or 0)
            data = json.loads(self.rfile.read(size).decode() or "{}")
        except Exception:
            data = {}
        _preview_enabled = bool(data.get("enabled"))
        if not _preview_enabled:
            _latest_preview = {
                "available": False,
                "reason": "preview_disabled",
                "updated_at": time.time(),
            }
        body = json.dumps({
            "ok": True,
            "analysis_preview_enabled": _preview_enabled,
            "live_handoff_enabled": False,
            "signal_enabled": False,
        }, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        _cors(self)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_status_server():
    server = ThreadingHTTPServer(("0.0.0.0", STATUS_PORT), StatusHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_forever():
    global _latest_preview
    print(
        "REAL_SIGNAL_START "
        f"preview_enabled={_preview_enabled} "
        f"enabled={REAL_SIGNAL_ENABLED} volume_configured={VOLUME > 0} "
        f"hourly_cap_configured={MAX_PUBLISH_PER_HOUR > 0} "
        "live_handoff_enabled=False",
        flush=True,
    )
    while True:
        a_reason = analysis_reason()
        if a_reason:
            _latest_preview = {
                "available": False,
                "reason": a_reason,
                "updated_at": time.time(),
            }
            print(f"real_analysis_wait reason={a_reason}", flush=True)
            time.sleep(POLL_SECONDS)
            continue

        try:
            feeds = fetch_market()
            _latest_preview = compute_preview(feeds)
            print(
                "real_analysis_preview "
                f"bar={_latest_preview.get('bar')} side={_latest_preview.get('side')} "
                f"score={_latest_preview.get('score')} h4={_latest_preview.get('h4')} "
                f"h1={_latest_preview.get('h1')} reason={_latest_preview.get('reason')}",
                flush=True,
            )
        except Exception as exc:
            detail = str(exc)
            reason = "market_closed_or_stale" if detail == "market_stale" else f"preview_error:{type(exc).__name__}"
            _latest_preview = {
                "available": False,
                "reason": reason,
                "updated_at": time.time(),
            }
            print(f"real_analysis_wait reason={reason} detail={type(exc).__name__}:{exc}", flush=True)

        # This build intentionally stops before any /publish call.
        if REAL_SIGNAL_ENABLED:
            print(f"real_signal_wait reason={config_reason() or 'live_handoff_not_enabled'}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    start_status_server()
    run_forever()
