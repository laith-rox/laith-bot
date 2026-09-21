"""Independent DEMO-only signal publisher for the Laith execution bridge.

This worker is intentionally isolated from V4 and the legacy Laith bot. It reads
XAU/USD 5-minute candles directly, evaluates seven mirrored conditions, and
publishes only 6/7-or-better BUY/SELL setups to the DEMO bridge.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import math
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BRIDGE_URL = os.getenv("BRIDGE_URL", "").strip().rstrip("/")
BRIDGE_PUBLISH_TOKEN = os.getenv("BRIDGE_PUBLISH_TOKEN", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
# Set to 0 to disable the hourly count cap; all execution checks still apply.
MAX_PUBLISH_PER_HOUR = int(os.getenv("MAX_PUBLISH_PER_HOUR", "2"))
ALLOW_STALE_MT5_STATE = os.getenv("ALLOW_STALE_MT5_STATE", "false").strip().lower() in {"1", "true", "yes", "on"}
SYMBOL = "XAU/USD"
YAHOO_SYMBOL = "GC=F"
VOLUME = 0.01
WORKER_VERSION = "bridge-unlimited-demo-v4"


def _ema(values, period):
    if not values:
        return []
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
        change = b - a
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss <= 1e-12:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(rows, period=14):
    if len(rows) < 2:
        return 0.0
    trs = []
    start = max(1, len(rows) - period)
    for i in range(start, len(rows)):
        prev_close = rows[i-1]["close"]
        high = rows[i]["high"]
        low = rows[i]["low"]
        trs.append(max(high-low, abs(high-prev_close), abs(low-prev_close)))
    return sum(trs) / len(trs) if trs else 0.0


def normalize_rows(values):
    """Convert Twelve Data newest-first values to oldest-first numeric rows.

    The newest item is intentionally dropped because it can still be the active
    five-minute candle. Signals are generated only from the latest closed bar.
    """
    if not isinstance(values, list) or len(values) < 30:
        raise ValueError("not_enough_market_rows")
    closed = values[1:]
    rows = []
    for item in reversed(closed):
        rows.append({
            "datetime": str(item.get("datetime", "")),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
        })
    return rows


def compute_signal(values):
    rows = normalize_rows(values)
    closes = [r["close"] for r in rows]
    ema8 = _ema(closes, 8)
    ema21 = _ema(closes, 21)
    last = rows[-1]
    close = last["close"]
    open_ = last["open"]
    rsi = _rsi(closes, 14)
    atr = _atr(rows, 14)

    recent_high = max(r["high"] for r in rows[-6:-1])
    recent_low = min(r["low"] for r in rows[-6:-1])

    buy = [
        ema8[-1] > ema21[-1],
        close > ema8[-1],
        ema8[-1] > ema8[-2],
        rsi >= 52.0,
        close > closes[-4],
        close > open_,
        close > recent_high,
    ]
    sell = [
        ema8[-1] < ema21[-1],
        close < ema8[-1],
        ema8[-1] < ema8[-2],
        rsi <= 48.0,
        close < closes[-4],
        close < open_,
        close < recent_low,
    ]
    buy_score = sum(bool(x) for x in buy)
    sell_score = sum(bool(x) for x in sell)

    side = None
    selected = None
    score = 0
    if buy_score >= 6 and buy_score > sell_score:
        side, selected, score = "BUY", buy, buy_score
    elif sell_score >= 6 and sell_score > buy_score:
        side, selected, score = "SELL", sell, sell_score

    # Commissioning risk is intentionally tight so the EA's default $2 test
    # budget remains the final gate at 0.01 lot.
    risk_distance = max(0.80, min(1.60, atr * 0.50 if atr > 0 else 1.20))
    if side == "BUY":
        sl = close - risk_distance
        tp = close + risk_distance * 1.5
    elif side == "SELL":
        sl = close + risk_distance
        tp = close - risk_distance * 1.5
    else:
        sl = tp = None

    return {
        "bar": last["datetime"],
        "side": side,
        "score": score,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "checks": {"BUY": buy, "SELL": sell},
        "reference_close": close,
        "rsi": rsi,
        "atr": atr,
        "risk_distance": risk_distance,
        "sl": sl,
        "tp": tp,
    }


def _json_request(url, method="GET", payload=None, headers=None, timeout=10):
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=request_headers)
    with urlopen(req, timeout=timeout) as response:
        raw = response.read().decode()
        return response.status, json.loads(raw) if raw else {}


def fetch_market_values():
    """Fetch keyless 5m gold-market candles.

    Yahoo's GC=F feed is used only as a directional proxy for this DEMO
    commissioning worker. Orders still execute only on the MT5 XAUUSD demo
    account, and the bridge/EA remain the final safety gate.
    """
    params = urlencode({"interval": "5m", "range": "5d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO_SYMBOL}?{params}"
    status, payload = _json_request(url, headers={"User-Agent": "Mozilla/5.0"})
    if status != 200:
        raise RuntimeError(f"market_data_http_{status}")
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("market_values_missing")

    rows = []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    for i, ts in enumerate(timestamps):
        try:
            o, h, l, cl = opens[i], highs[i], lows[i], closes[i]
            if None in (o, h, l, cl):
                continue
            rows.append({
                "datetime": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "open": f"{float(o):.5f}",
                "high": f"{float(h):.5f}",
                "low": f"{float(l):.5f}",
                "close": f"{float(cl):.5f}",
            })
        except (IndexError, TypeError, ValueError):
            continue
    if len(rows) < 31:
        raise RuntimeError("not_enough_market_rows")
    return list(reversed(rows))


def bridge_health():
    status, payload = _json_request(f"{BRIDGE_URL}/health")
    if status != 200:
        raise RuntimeError(f"bridge_health_http_{status}")
    return payload


def fetch_spot_price():
    """Fetch a fresh keyless XAU/USD spot reference for execution levels."""
    fresh = int(time.time())
    status, payload = _json_request(
        f"https://xaus.com/api/v1/spot?compact=1&fresh={fresh}",
        headers={"User-Agent": "LaithBridgeCommissioning/1.0"},
    )
    if status != 200:
        raise RuntimeError(f"spot_http_{status}")
    state = payload.get("data_state") or {}
    if state.get("status") not in ("fresh", "stale"):
        raise RuntimeError("spot_unavailable")
    age = state.get("age_seconds")
    if state.get("status") == "stale" and age is not None and float(age) > 120:
        raise RuntimeError(f"spot_too_stale:{age}")
    price = float(payload.get("spot_usd_oz") or 0)
    if price <= 0:
        raise RuntimeError("spot_price_missing")
    return price


def publish_signal(signal):
    side = signal["side"]
    spot = fetch_spot_price()
    risk_distance = float(signal["risk_distance"])
    if side == "BUY":
        sl = spot - risk_distance
        tp = spot + risk_distance * 1.5
    else:
        sl = spot + risk_distance
        tp = spot - risk_distance * 1.5
    payload = {
        "mode": "DEMO",
        "key": f"auto:{signal['bar'].replace(' ','T').replace(':','').replace('-','')}:{side}",
        "symbol": "XAUUSD",
        "side": side,
        "volume": VOLUME,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "forced": False,
        "checks": signal["checks"],
    }
    status, response = _json_request(
        f"{BRIDGE_URL}/publish",
        method="POST",
        payload=payload,
        headers={"X-Publish-Token": BRIDGE_PUBLISH_TOKEN},
    )
    return status, response, payload["key"]


def validate_config():
    if MAX_PUBLISH_PER_HOUR < 0:
        raise RuntimeError("invalid_max_publish_per_hour")
    missing = [
        name for name, value in (
            ("BRIDGE_URL", BRIDGE_URL),
            ("BRIDGE_PUBLISH_TOKEN", BRIDGE_PUBLISH_TOKEN),
        ) if not value
    ]
    if missing:
        raise RuntimeError("missing_config:" + ",".join(missing))


def run_forever():
    validate_config()
    print(
        f"bridge_signal_worker_started version={WORKER_VERSION} symbol={SYMBOL} interval=5m "
        f"strict=6/7 volume={VOLUME:.2f} max_publish_per_hour={MAX_PUBLISH_PER_HOUR} "
        f"allow_stale_mt5_state={ALLOW_STALE_MT5_STATE}",
        flush=True,
    )
    last_bar = None
    publishes = deque()

    while True:
        try:
            now = time.time()
            while publishes and now - publishes[0] >= 3600:
                publishes.popleft()

            health = bridge_health()
            if not health.get("enabled"):
                print("bridge_signal_skip reason=bridge_disabled", flush=True)
                time.sleep(POLL_SECONDS)
                continue
            if not health.get("client_state_fresh"):
                if not ALLOW_STALE_MT5_STATE:
                    print("bridge_signal_skip reason=mt5_state_stale", flush=True)
                    time.sleep(POLL_SECONDS)
                    continue
                print("bridge_signal_commissioning mt5_state=stale local_ea_safety_required=true", flush=True)
            if health.get("position_open") or int(health.get("pending", 0) or 0) > 0:
                print("bridge_signal_skip reason=position_or_pending", flush=True)
                time.sleep(POLL_SECONDS)
                continue
            if MAX_PUBLISH_PER_HOUR > 0 and len(publishes) >= MAX_PUBLISH_PER_HOUR:
                print("bridge_signal_skip reason=hourly_publish_cap", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            signal = compute_signal(fetch_market_values())
            if signal["bar"] == last_bar:
                time.sleep(POLL_SECONDS)
                continue
            last_bar = signal["bar"]

            if not signal["side"]:
                print(
                    f"bridge_signal_wait bar={signal['bar']} buy={signal['buy_score']}/7 "
                    f"sell={signal['sell_score']}/7 rsi={signal['rsi']:.1f}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            status, response, key = publish_signal(signal)
            if status == 201 and response.get("ok") is True:
                if MAX_PUBLISH_PER_HOUR > 0:
                    publishes.append(time.time())
                print(
                    f"bridge_signal_published key={key} side={signal['side']} "
                    f"score={signal['score']}/7 reference_proxy={signal['reference_close']:.2f} "
                    f"risk_distance={signal['risk_distance']:.2f}",
                    flush=True,
                )
            else:
                print(
                    f"bridge_signal_publish_rejected status={status} "
                    f"reason={response.get('reason','unknown')}",
                    flush=True,
                )
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            print(f"bridge_signal_error type={type(exc).__name__} detail={exc}", flush=True)
        except Exception as exc:
            print(f"bridge_signal_error type={type(exc).__name__} detail={exc}", flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()
