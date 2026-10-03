"""REAL signal worker mirrored from the currently deployed DEMO engine.

The decision engine lives in real_analysis_engine.py and is kept byte-for-byte
aligned with the deployed DEMO bridge_signal_worker.py. This wrapper changes
only transport/configuration from DEMO to REAL and remains fail-closed.
"""
from __future__ import annotations

from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError

import real_analysis_engine as engine
import gigi_regime
import gigi_intermarket
import gigi_macro
import gigi_context
import gigi_liquidity
import gigi_positioning
import gigi_volatility
import gigi_etf
import gigi_crowding

REAL_ANALYSIS_PREVIEW_ENABLED = os.getenv("REAL_ANALYSIS_PREVIEW_ENABLED", "false").strip().lower() == "true"
REAL_SIGNAL_ENABLED = os.getenv("REAL_SIGNAL_ENABLED", "false").strip().lower() == "true"
REAL_LIVE_HANDOFF_ENABLED = os.getenv("REAL_LIVE_HANDOFF_ENABLED", "false").strip().lower() == "true"
BRIDGE_URL = os.getenv("REAL_BRIDGE_URL", "").strip().rstrip("/")
PUBLISH_TOKEN = os.getenv("REAL_BRIDGE_PUBLISH_TOKEN", "").strip()
VOLUME = float(os.getenv("REAL_VOLUME", "0") or 0)
POLL_SECONDS = int(os.getenv("REAL_POLL_SECONDS", "30") or 30)
MAX_PUBLISH_PER_HOUR = int(os.getenv("REAL_MAX_PUBLISH_PER_HOUR", "0") or 0)
STATUS_PORT = int(os.getenv("PORT", "8080"))
ALLOWED_ORIGIN = os.getenv(
    "REAL_STATUS_ALLOWED_ORIGIN",
    "https://laith-app-production.up.railway.app",
).strip()
MIRRORED_DEMO_RELEASE = os.getenv(
    "REAL_MIRRORED_DEMO_RELEASE",
    "073aca3a062933999f0bc0cf82654b1e9b4fe720",
).strip()

_preview_enabled = REAL_ANALYSIS_PREVIEW_ENABLED
_latest_preview = {
    "available": False,
    "reason": "preview_disabled",
    "updated_at": 0.0,
}

# Point the exact DEMO decision module at the REAL transport.
engine.BRIDGE_URL = BRIDGE_URL
engine.BRIDGE_PUBLISH_TOKEN = PUBLISH_TOKEN
engine.POLL_SECONDS = POLL_SECONDS
engine.MAX_PUBLISH_PER_HOUR = MAX_PUBLISH_PER_HOUR
engine.ALLOW_STALE_MT5_STATE = False
engine.VOLUME = VOLUME
engine.WORKER_VERSION = "real-mirror-" + MIRRORED_DEMO_RELEASE[:12]


def config_reason():
    if not REAL_SIGNAL_ENABLED:
        return "real_signal_disabled"
    if not REAL_LIVE_HANDOFF_ENABLED:
        return "real_live_handoff_disabled"
    if not BRIDGE_URL or not PUBLISH_TOKEN:
        return "real_signal_auth_not_configured"
    if abs(VOLUME - 0.01) > 1e-9:
        return "real_volume_must_match_demo_0_01"
    if MAX_PUBLISH_PER_HOUR != 6:
        return "real_hourly_cap_must_match_demo_6"
    return None


def analysis_reason():
    if not _preview_enabled:
        return "preview_disabled"
    if not BRIDGE_URL:
        return "preview_bridge_not_configured"
    return None


def bridge_health():
    last_error = None
    for attempt in range(3):
        try:
            status, payload = engine._json_request(f"{BRIDGE_URL}/health")
            if status == 200:
                return payload
            last_error = RuntimeError(f"bridge_health_http_{status}")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(2)
    raise RuntimeError(f"bridge_health_unavailable:{last_error}")


PALESTINE_OFFSET = timedelta(hours=3)
DAY_ENTRY_START_MINUTE = 5 * 60
DAY_ENTRY_END_MINUTE = 20 * 60
MAIN_LONDON_START_MINUTE = 10 * 60
MAIN_LONDON_END_MINUTE = 13 * 60
MAIN_US_START_MINUTE = 15 * 60 + 20
MAIN_US_END_MINUTE = 18 * 60


def signal_local_minute(signal):
    """Resolve the closed broker candle into Palestine local clock time."""
    raw = str(signal.get("bar") or "")
    if not raw:
        raise RuntimeError("signal_bar_missing")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(timezone.utc) + PALESTINE_OFFSET
    return local.hour * 60 + local.minute


def main_session_name(minute):
    if MAIN_LONDON_START_MINUTE <= minute < MAIN_LONDON_END_MINUTE:
        return "LONDON_MAIN"
    if MAIN_US_START_MINUTE <= minute < MAIN_US_END_MINUTE:
        return "US_MAIN"
    if DAY_ENTRY_START_MINUTE <= minute < DAY_ENTRY_END_MINUTE:
        return "DAY_MAIN"
    return None


def session_block_reason(signal):
    """Allow both MAIN and SNIPER during the requested 05:00-20:00 window."""
    mode = "MAIN" if str(signal.get("mode") or "").upper() == "MAIN" else "SNIPER"
    minute = signal_local_minute(signal)
    if DAY_ENTRY_START_MINUTE <= minute < DAY_ENTRY_END_MINUTE:
        return None
    return "main_session_closed" if mode == "MAIN" else "sniper_session_closed"


def execution_block_reason(health):
    if health.get("mode") != "REAL":
        return "bridge_not_real"
    if not health.get("client_state_fresh"):
        return "mt5_state_stale"
    if not health.get("market_fresh"):
        return "market_closed_or_stale"
    if int(health.get("pending", 0) or 0) >= 2:
        return "pending_command_limit"
    if not health.get("ready"):
        blockers = health.get("readiness_blockers") or []
        return "bridge_not_ready:" + (str(blockers[0]) if blockers else "unknown")
    return None


def signal_fingerprint(signal, copy_index=1):
    """Stable identity for one independent setup.

    Same candle + mode + side + reason + copy is one idea. A different reason
    or different mode on the same candle is allowed to be a separate idea.
    """
    side=str(signal.get("side") or "WAIT").upper()
    mode="MAIN" if str(signal.get("mode") or "").upper()=="MAIN" else "SNIPER"
    bar=str(signal.get("bar") or "")
    reason=str(signal.get("reason") or "")
    digest=hashlib.sha1(reason.encode("utf-8")).hexdigest()[:8]
    return f"{bar}|{mode}|{side}|{digest}|C{int(copy_index)}"


def reason_tag(signal):
    return hashlib.sha1(str(signal.get("reason") or "").encode("utf-8")).hexdigest()[:8]


def publish_signal(signal, spot_override=None, copy_index=1):
    session_reason = session_block_reason(signal)
    if session_reason:
        raise RuntimeError(session_reason)
    if str(signal.get("mode") or "").upper() == "MAIN" and not bool(signal.get("native_h4_reopen_ready", True)):
        raise RuntimeError("main_native_h4_reopen_warmup")
    side = signal["side"]
    spot = float(spot_override or 0)
    if spot <= 0:
        raise RuntimeError("real_mt5_price_missing")
    risk_distance = float(signal["risk_distance"])
    if side == "BUY":
        sl = spot - risk_distance
        tp = spot + risk_distance * float(signal.get("target_r", 1.5))
    else:
        sl = spot + risk_distance
        tp = spot - risk_distance * float(signal.get("target_r", 1.5))
    trade_mode = "MAIN" if str(signal.get("mode") or "").upper() == "MAIN" else "SNIPER"
    strength = sum(bool(x) for x in signal["checks"][side])
    payload = {
        "mode": "REAL",
        "trade_mode": trade_mode,
        "key": f"auto:{signal['bar'].replace(' ','T').replace(':','').replace('-','')}:{trade_mode}:{side}:R{reason_tag(signal)}:C{copy_index}:S{strength}",
        "symbol": "XAUUSD",
        "side": side,
        "volume": VOLUME,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "forced": False,
        "checks": signal["checks"],
    }
    if trade_mode == "MAIN":
        payload["analysis"] = signal.get("analysis", {})
    status, response = engine._json_request(
        f"{BRIDGE_URL}/publish",
        method="POST",
        payload=payload,
        headers={"X-Publish-Token": PUBLISH_TOKEN},
    )
    return status, response, payload["key"]


def preview_payload(signal):
    side = signal.get("side") or "WAIT"
    return {
        "available": True,
        "side": side,
        "mode": signal.get("mode"),
        "reason": signal.get("reason"),
        "score": int(signal.get("score") or 0),
        "buy_score": int(signal.get("buy_score") or 0),
        "sell_score": int(signal.get("sell_score") or 0),
        "bar": signal.get("bar"),
        "reference_close": signal.get("reference_close"),
        "risk_distance": signal.get("risk_distance"),
        "rsi": round(float(signal.get("rsi") or 0), 1),
        "h4": (signal.get("mtf") or {}).get("h4_bias"),
        "native_h4_reopen_ready": bool(signal.get("native_h4_reopen_ready", True)),
        "regime": signal.get("regime") or {},
        "intermarket": signal.get("intermarket") or {},
        "macro": signal.get("macro") or {},
        "liquidity": signal.get("liquidity") or {},
        "positioning": signal.get("positioning") or {},
        "volatility": signal.get("volatility") or {},
        "etf": signal.get("etf") or {},
        "crowding": signal.get("crowding") or {},
        "gigi_context": signal.get("gigi_context") or {},
        "session": main_session_name(signal_local_minute(signal)) if str(signal.get("mode") or "").upper() == "MAIN" else "DAY_SNIPER",
        "live_handoff_enabled": REAL_LIVE_HANDOFF_ENABLED,
        "mirrored_demo_release": MIRRORED_DEMO_RELEASE,
        "updated_at": time.time(),
    }


def status_payload():
    return {
        "ok": True,
        "mode": "REAL",
        "analysis_preview_enabled": _preview_enabled,
        "enabled": REAL_SIGNAL_ENABLED,
        "volume_configured": abs(VOLUME - 0.01) <= 1e-9,
        "hourly_cap_configured": MAX_PUBLISH_PER_HOUR == 6,
        "bridge_configured": bool(BRIDGE_URL and PUBLISH_TOKEN),
        "analysis_reason": analysis_reason(),
        "config_reason": config_reason(),
        "live_handoff_enabled": REAL_LIVE_HANDOFF_ENABLED,
        "mirrored_demo_release": MIRRORED_DEMO_RELEASE,
        "preview": _latest_preview,
    }


def _cors(handler):
    origin = handler.headers.get("Origin", "")
    if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN:
        handler.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        handler.send_header("Vary", "Origin")


class StatusHandler(BaseHTTPRequestHandler):
    server_version = "LaithRealSignalStatus/2.0"

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
            self.send_response(404); self.end_headers(); return
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
            self.send_response(404); self.end_headers(); return
        if not ALLOWED_ORIGIN or self.headers.get("Origin", "") != ALLOWED_ORIGIN:
            body = b'{"ok":false,"reason":"trusted_app_origin_required"}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        try:
            size = int(self.headers.get("Content-Length", "0") or 0)
            data = json.loads(self.rfile.read(size).decode() or "{}")
        except Exception:
            data = {}
        _preview_enabled = bool(data.get("enabled"))
        if not _preview_enabled:
            _latest_preview = {"available": False, "reason": "preview_disabled", "updated_at": time.time()}
        body = json.dumps({
            "ok": True,
            "analysis_preview_enabled": _preview_enabled,
            "live_handoff_enabled": REAL_LIVE_HANDOFF_ENABLED,
            "signal_enabled": REAL_SIGNAL_ENABLED,
        }, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        _cors(self)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)


def start_status_server():
    server = ThreadingHTTPServer(("0.0.0.0", STATUS_PORT), StatusHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_forever():
    global _latest_preview
    print(
        "REAL_SIGNAL_START "
        f"mirrored_demo_release={MIRRORED_DEMO_RELEASE} "
        f"preview_enabled={_preview_enabled} enabled={REAL_SIGNAL_ENABLED} "
        f"live_handoff_enabled={REAL_LIVE_HANDOFF_ENABLED} volume={VOLUME:.2f} "
        f"max_publish_per_hour={MAX_PUBLISH_PER_HOUR}",
        flush=True,
    )
    last_bar = None
    last_sniper_side = None
    last_sniper_score = 0
    last_sniper_bar = None
    publishes = deque()
    published_fingerprints = deque(maxlen=500)

    while True:
        try:
            now = time.time()
            while publishes and now - publishes[0] >= 3600:
                publishes.popleft()

            if not _preview_enabled and not REAL_SIGNAL_ENABLED:
                time.sleep(POLL_SECONDS)
                continue

            health = bridge_health()
            if not health.get("market_fresh"):
                _latest_preview = {
                    "available": False,
                    "reason": "market_closed_or_stale",
                    "updated_at": time.time(),
                }
                time.sleep(POLL_SECONDS)
                continue

            feeds = engine.fetch_multitimeframe_values()
            try:
                engine.validate_market_feed_freshness(feeds)
            except RuntimeError as exc:
                _latest_preview = {
                    "available": False,
                    "reason": str(exc),
                    "updated_at": time.time(),
                }
                time.sleep(POLL_SECONDS)
                continue

            signal = engine.compute_signal(feeds["5m"])
            mtf = engine.analyze_structure(
                engine.normalize_rows(feeds["5m"]),
                engine.normalize_rows(feeds["15m"]),
                engine.normalize_rows(feeds["h4"]),
            )
            signal = engine.apply_main_structure(signal, mtf)
            signal = engine.recover_m15_continuation(signal, health)
            signal = engine.recover_strong_structural_entry(signal, health)
            signal["native_h4_reopen_ready"] = engine.native_h4_reopen_ready(feeds["h4"])
            signal["regime"] = gigi_regime.classify(
                engine.normalize_rows(feeds["5m"]),
                engine.normalize_rows(feeds["15m"]),
                engine.normalize_rows(feeds["h4"]),
            )
            signal["intermarket"] = gigi_intermarket.analyze(
                engine.normalize_rows(feeds["15m"]),
                feeds.get("intermarket") or {},
            )
            signal["macro"] = gigi_macro.context(time.time())
            signal["liquidity"] = gigi_liquidity.analyze(
                engine.normalize_rows(feeds["5m"]),
                engine.normalize_rows(feeds["15m"]),
            )
            signal["positioning"] = gigi_positioning.fetch(time.time())
            signal["volatility"] = gigi_volatility.analyze(
                engine.normalize_rows(feeds["15m"])
            )
            signal["etf"] = gigi_etf.fetch(time.time())
            signal["crowding"] = gigi_crowding.analyze(
                signal.get("positioning"),
                signal.get("volatility"),
                signal.get("liquidity"),
                signal.get("etf"),
                signal.get("regime"),
            )
            signal["gigi_context"] = gigi_context.evaluate(
                signal.get("side"),
                signal.get("regime"),
                signal.get("intermarket"),
                signal.get("macro"),
                signal.get("liquidity"),
                signal.get("positioning"),
                signal.get("volatility"),
                signal.get("etf"),
                signal.get("crowding"),
            )

            if _preview_enabled:
                _latest_preview = preview_payload(signal)

            if signal["bar"] == last_bar:
                time.sleep(POLL_SECONDS)
                continue
            last_bar = signal["bar"]

            if not REAL_SIGNAL_ENABLED or not REAL_LIVE_HANDOFF_ENABLED:
                print(
                    f"real_signal_preview bar={signal['bar']} side={signal.get('side') or 'WAIT'} "
                    f"buy={signal['buy_score']}/7 sell={signal['sell_score']}/7 "
                    f"reason={signal.get('reason')}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            reason = config_reason()
            if reason:
                print(f"real_signal_skip reason={reason}", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            block_reason = execution_block_reason(health)
            if block_reason:
                print(f"real_signal_skip reason={block_reason}", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            if MAX_PUBLISH_PER_HOUR > 0 and len(publishes) >= MAX_PUBLISH_PER_HOUR:
                print("real_signal_skip reason=hourly_publish_cap", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            if not signal["side"]:
                print(
                    f"real_signal_wait bar={signal['bar']} buy={signal['buy_score']}/7 "
                    f"sell={signal['sell_score']}/7 close={signal['reference_close']:.2f} "
                    f"rsi={signal['rsi']:.1f} reason={signal.get('reason')} "
                    f"h4={signal.get('mtf',{}).get('h4_bias')}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            if str(signal.get("mode") or "").upper() == "MAIN" and not signal.get("native_h4_reopen_ready"):
                print(
                    f"real_signal_skip reason=main_native_h4_reopen_warmup "
                    f"bar={signal.get('bar')}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            session_reason = session_block_reason(signal)
            if session_reason:
                print(
                    f"real_signal_skip reason={session_reason} "
                    f"mode={signal.get('mode')} bar={signal.get('bar')}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            chase_reason = engine.sniper_chase_block_reason(
                signal, last_sniper_side, last_sniper_score, last_sniper_bar
            )
            if chase_reason:
                print(
                    f"real_signal_skip reason={chase_reason} side={signal.get('side')} "
                    f"score={engine.signal_strength(signal)}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            mt5_spot = float(health.get("price") or 0)
            copies = engine.same_entry_copies(signal, health)
            if copies <= 0:
                print(
                    f"real_signal_skip reason=aggregate_risk_budget "
                    f"budget={health.get('effective_risk_budget_usd')} "
                    f"used={health.get('total_position_risk_usd')} "
                    f"required={signal.get('risk_distance')}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            slots = MAX_PUBLISH_PER_HOUR - len(publishes) if MAX_PUBLISH_PER_HOUR > 0 else copies
            for copy_index in range(1, min(copies, slots) + 1):
                fingerprint = signal_fingerprint(signal, copy_index)
                if fingerprint in published_fingerprints:
                    print(
                        f"real_signal_skip reason=duplicate_signal_fingerprint "
                        f"fingerprint={fingerprint}",
                        flush=True,
                    )
                    continue
                status, response, key = publish_signal(signal, mt5_spot, copy_index)
                if status == 201 and response.get("ok") is True:
                    published_fingerprints.append(fingerprint)
                    publishes.append(time.time())
                    if str(signal.get("mode") or "").upper() != "MAIN":
                        last_sniper_side = signal.get("side")
                        last_sniper_score = engine.signal_strength(signal)
                        last_sniper_bar = signal.get("bar")
                    print(
                        f"real_signal_published key={key} side={signal['side']} "
                        f"mode={signal.get('mode')} confidence={signal.get('confidence')} "
                        f"risk_distance={signal['risk_distance']:.2f}",
                        flush=True,
                    )
                else:
                    print(
                        f"real_signal_publish_rejected status={status} "
                        f"reason={response.get('reason','unknown')}",
                        flush=True,
                    )
                    break

        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            print(f"real_signal_error type={type(exc).__name__} detail={exc}", flush=True)
        except Exception as exc:
            print(f"real_signal_error type={type(exc).__name__} detail={exc}", flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    start_status_server()
    run_forever()
