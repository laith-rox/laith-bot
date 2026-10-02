"""Future REAL signal runner. Disabled and fail-closed by default.

When explicitly configured later it reuses the tested gold analysis engine, but
publishes REAL commands only to the isolated REAL bridge.
"""
from __future__ import annotations

from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REAL_SIGNAL_ENABLED = os.getenv("REAL_SIGNAL_ENABLED", "false").strip().lower() == "true"
LIVE_HANDOFF_ENABLED = os.getenv("REAL_LIVE_HANDOFF_ENABLED", "false").strip().lower() == "true"
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

from real_analysis_engine import compute_signal, normalize_rows, apply_main_structure
from multi_timeframe_structure import analyze_structure


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
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"detail": raw[:200]}
        return exc.code, payload


def config_reason():
    if not REAL_SIGNAL_ENABLED:
        return "real_signal_disabled"
    if not LIVE_HANDOFF_ENABLED:
        return "real_live_handoff_disabled"
    if not BRIDGE_URL or not PUBLISH_TOKEN:
        return "real_signal_auth_not_configured"
    if VOLUME <= 0:
        return "real_signal_volume_not_configured"
    if MAX_PUBLISH_PER_HOUR <= 0:
        return "real_signal_hourly_cap_not_configured"
    return None


def bridge_health():
    status, payload = _json_request(f"{BRIDGE_URL}/health")
    if status != 200:
        raise RuntimeError(f"bridge_health_http_{status}")
    return payload


def status_payload():
    return {
        "ok": True,
        "mode": "REAL",
        "enabled": REAL_SIGNAL_ENABLED,
        "live_handoff_enabled": LIVE_HANDOFF_ENABLED,
        "volume_configured": VOLUME > 0,
        "hourly_cap_configured": MAX_PUBLISH_PER_HOUR > 0,
        "bridge_configured": bool(BRIDGE_URL and PUBLISH_TOKEN),
        "config_reason": config_reason(),
    }


def _cors(handler):
    origin = handler.headers.get("Origin", "")
    if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN:
        handler.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        handler.send_header("Vary", "Origin")


class StatusHandler(BaseHTTPRequestHandler):
    server_version = "LaithRealSignalStatus/1.0"

    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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


def start_status_server():
    server = ThreadingHTTPServer(("0.0.0.0", STATUS_PORT), StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_forever():
    print(
        "REAL_SIGNAL_START "
        f"enabled={REAL_SIGNAL_ENABLED} volume_configured={VOLUME > 0} "
        f"hourly_cap_configured={MAX_PUBLISH_PER_HOUR > 0}",
        flush=True,
    )
    publishes = deque()
    last_bar = None
    while True:
        reason = config_reason()
        if reason:
            print(f"real_signal_wait reason={reason}", flush=True)
            time.sleep(POLL_SECONDS)
            continue

        health = bridge_health()
        if not health.get("ready"):
            print(
                "real_signal_wait reason=real_bridge_not_ready "
                f"armed={health.get('armed')} execution_enabled={health.get('execution_enabled')} "
                f"configured={health.get('configured')}",
                flush=True,
            )
            time.sleep(POLL_SECONDS)
            continue
        if not health.get("client_state_fresh") or not health.get("market_fresh"):
            print(
                "real_signal_wait reason=real_mt5_data_stale "
                f"state_fresh={health.get('client_state_fresh')} market_fresh={health.get('market_fresh')}",
                flush=True,
            )
            time.sleep(POLL_SECONDS)
            continue

        now = time.time()
        while publishes and now - publishes[0] >= 3600:
            publishes.popleft()
        if len(publishes) >= MAX_PUBLISH_PER_HOUR:
            print("real_signal_wait reason=hourly_publish_cap", flush=True)
            time.sleep(POLL_SECONDS)
            continue

        status, market = _json_request(f"{BRIDGE_URL}/market")
        if status != 200 or not market.get("ok"):
            print(f"real_signal_wait reason=market_http_{status}", flush=True)
            time.sleep(POLL_SECONDS)
            continue
        feeds = {"5m": market.get("m5"), "15m": market.get("m15"), "1h": market.get("h1")}
        if not all(isinstance(v, list) and len(v) >= 30 for v in feeds.values()):
            print("real_signal_wait reason=market_rows_missing", flush=True)
            time.sleep(POLL_SECONDS)
            continue

        signal = compute_signal(feeds["5m"])
        mtf = analyze_structure(
            normalize_rows(feeds["5m"]),
            normalize_rows(feeds["15m"]),
            normalize_rows(feeds["1h"]),
        )
        signal = apply_main_structure(signal, mtf)

        if signal["bar"] == last_bar:
            time.sleep(POLL_SECONDS)
            continue
        last_bar = signal["bar"]

        if not signal.get("side"):
            print(
                f"real_signal_wait bar={signal['bar']} reason={signal.get('reason')} "
                f"buy={signal.get('buy_score')}/7 sell={signal.get('sell_score')}/7",
                flush=True,
            )
            time.sleep(POLL_SECONDS)
            continue

        spot = float(health.get("price") or 0)
        risk = float(signal.get("risk_distance") or 0)
        if spot <= 0 or risk <= 0:
            print("real_signal_wait reason=invalid_spot_or_risk", flush=True)
            time.sleep(POLL_SECONDS)
            continue

        side = signal["side"]
        target_r = float(signal.get("target_r") or 1.0)
        if side == "BUY":
            sl, tp = spot - risk, spot + risk * target_r
        else:
            sl, tp = spot + risk, spot - risk * target_r
        trade_mode = "MAIN" if str(signal.get("mode") or "").upper() == "MAIN" else "SNIPER"
        selected = (signal.get("checks") or {}).get(side) or []
        strength = sum(bool(x) for x in selected)
        key = f"real:{signal['bar'].replace(' ','T').replace(':','').replace('-','')}:{trade_mode}:{side}:S{strength}"
        payload = {
            "mode": "REAL",
            "trade_mode": trade_mode,
            "key": key,
            "symbol": "XAUUSD",
            "side": side,
            "volume": VOLUME,
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "forced": False,
            "checks": signal.get("checks") or {},
        }
        status, response = _json_request(
            f"{BRIDGE_URL}/publish",
            method="POST",
            payload=payload,
            headers={"X-Publish-Token": PUBLISH_TOKEN},
        )
        if status == 201 and response.get("ok"):
            publishes.append(time.time())
            print(
                f"real_signal_published key={key} side={side} mode={trade_mode} "
                f"score={strength}/7 risk_distance={risk:.2f}",
                flush=True,
            )
        else:
            print(
                f"real_signal_publish_rejected status={status} "
                f"reason={response.get('reason','unknown')}",
                flush=True,
            )
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    start_status_server()
    run_forever()
