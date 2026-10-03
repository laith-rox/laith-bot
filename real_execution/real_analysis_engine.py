"""Independent DEMO-only signal publisher for the Laith execution bridge.

This worker is intentionally isolated from V4 and the legacy Laith bot. It reads
XAU/USD 5-minute candles directly, evaluates seven mirrored conditions, and
publishes 5/7-or-better BUY/SELL setups for the fast DEMO mode to the DEMO bridge.
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
from email.utils import parsedate_to_datetime
from adaptive_sniper_engine import decide
from multi_timeframe_structure import analyze_structure
from technical_confirmation import analyze as analyze_technical

BRIDGE_URL = os.getenv("BRIDGE_URL", "").strip().rstrip("/")
BRIDGE_PUBLISH_TOKEN = os.getenv("BRIDGE_PUBLISH_TOKEN", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))
# Set to 0 to disable the hourly count cap; all execution checks still apply.
MAX_PUBLISH_PER_HOUR = int(os.getenv("MAX_PUBLISH_PER_HOUR", "2"))
ALLOW_STALE_MT5_STATE = os.getenv("ALLOW_STALE_MT5_STATE", "false").strip().lower() in {"1", "true", "yes", "on"}
SYMBOL = "XAU/USD"
YAHOO_SYMBOL = "GC=F"
VOLUME = 0.01
_LAST_GOOD_MARKET_ROWS = None
_LAST_GOOD_MARKET_AT = 0.0
_MTF_CACHE = {}
WORKER_VERSION = "bridge-m15-continuation-v1"


def closed_bar_key(value):
    """Broker timestamps can differ by seconds for the same closed M5 candle."""
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(minute=dt.minute // 5 * 5, second=0, microsecond=0).isoformat(sep=" ")


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
    """Normalize provider candles to oldest-first closed rows.

    Sources do not share one array order: the MT5 relay is oldest-first while
    Yahoo/Twelve-style fallbacks can be newest-first. Sort by the candle's own
    timestamp instead of assuming source order, then drop only the newest
    candle because it may still be active.
    """
    if not isinstance(values, list) or len(values) < 30:
        raise ValueError("not_enough_market_rows")
    rows = []
    for item in values:
        dt = str(item.get("datetime", "")).replace(".", "-", 2)
        if not dt:
            continue
        rows.append({
            "datetime": dt,
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "tick_volume": float(item.get("tick_volume") or 0),
        })
    if len(rows) < 30:
        raise ValueError("not_enough_market_rows")
    rows.sort(key=lambda row: datetime.fromisoformat(row["datetime"].replace("Z", "+00:00")))
    return rows[:-1]


MAX_CLOSED_BAR_AGE_SECONDS = {"5m": 15 * 60, "15m": 40 * 60, "h4": 9 * 60 * 60}
REOPEN_MIN_CLOSED_BARS = {"5m": 3, "15m": 1, "h4": 0}
# H4 must be broker-native and the latest H4 candle used by analysis must be closed.
# We never synthesize H4 from smaller candles in REAL mode.
REQUIRE_NATIVE_H4 = True
EXPECTED_BAR_SECONDS = {"5m": 5 * 60, "15m": 15 * 60, "h4": 4 * 60 * 60}


def _rows_after_last_gap(rows, expected_seconds):
    """Count completed candles after the latest market closure/discontinuity."""
    if len(rows) < 2:
        return len(rows)
    last_gap_index = -1
    for i in range(1, len(rows)):
        a = datetime.fromisoformat(str(rows[i-1]["datetime"]).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(rows[i]["datetime"]).replace("Z", "+00:00"))
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
        if b.tzinfo is None:
            b = b.replace(tzinfo=timezone.utc)
        gap = b.timestamp() - a.timestamp()
        # 3x timeframe catches the daily maintenance break and weekend closure,
        # without treating one missing bar as a reopen event.
        if gap > expected_seconds * 3:
            last_gap_index = i
    if last_gap_index < 0:
        return len(rows)
    return len(rows) - last_gap_index


def native_h4_reopen_ready(values):
    """Require one newly CLOSED broker-native H4 candle after a long closure.

    The newest MT5 H4 row is the active candle, so it is deliberately excluded
    from the completed-after-gap count. This prevents a weekend/daily reopen
    from promoting an old pre-close H4 candle into a new MAIN setup.
    """
    if not isinstance(values, list) or len(values) < 3:
        return False
    rows = []
    for item in values:
        raw = str(item.get("datetime") or "").replace(".", "-", 2)
        if not raw:
            continue
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        rows.append(dt)
    rows.sort()
    if len(rows) < 3:
        return False
    last_gap_index = -1
    for i in range(1, len(rows)):
        if (rows[i] - rows[i-1]).total_seconds() > EXPECTED_BAR_SECONDS["h4"] * 3:
            last_gap_index = i
    if last_gap_index < 0:
        return True
    rows_after_gap_including_active = len(rows) - last_gap_index
    completed_after_gap = max(0, rows_after_gap_including_active - 1)
    return completed_after_gap >= 1


def validate_market_feed_freshness(feeds, now_ts=None):
    """Reject stale broker candles before any signal logic can run."""
    now_ts = time.time() if now_ts is None else float(now_ts)
    ages = {}
    for timeframe, max_age in MAX_CLOSED_BAR_AGE_SECONDS.items():
        values = feeds.get(timeframe) if isinstance(feeds, dict) else None
        rows = normalize_rows(values or [])
        latest = rows[-1]["datetime"]
        parsed = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = now_ts - parsed.timestamp()
        if age < -120:
            raise RuntimeError(f"market_clock_ahead:{timeframe}:age={age:.0f}s:last={latest}")
        if age > max_age:
            raise RuntimeError(f"stale_market_data:{timeframe}:age={age:.0f}s:last={latest}")

        closed_after_gap = _rows_after_last_gap(
            rows, EXPECTED_BAR_SECONDS[timeframe]
        )
        minimum = REOPEN_MIN_CLOSED_BARS[timeframe]
        if closed_after_gap < minimum:
            raise RuntimeError(
                f"market_reopen_warmup:{timeframe}:"
                f"closed_after_gap={closed_after_gap}:required={minimum}"
            )
        ages[timeframe] = age
    return ages


def compute_signal(values):
    rows = normalize_rows(values)
    tech = analyze_technical(rows)
    closes = [r["close"] for r in rows]
    ema8, ema21, ema55 = _ema(closes, 8), _ema(closes, 21), _ema(closes, 55)
    last = rows[-1]; close = last["close"]; open_ = last["open"]
    rsi = _rsi(closes, 14); atr = _atr(rows, 14)
    atr_samples = [_atr(rows[:i], 14) for i in range(max(16, len(rows)-12), len(rows)+1)]
    atr_samples = [x for x in atr_samples if x > 0]
    atr_baseline = sum(atr_samples)/len(atr_samples) if atr_samples else atr
    recent_high = max(r["high"] for r in rows[-6:-1])
    recent_low = min(r["low"] for r in rows[-6:-1])
    momentum = close - closes[-4]
    # Compact indicator stack: trend + trend strength/direction are primary;
    # RSI and volume confirm rather than creating a trade by themselves.
    # Missing broker volume is neutral so a provider fallback cannot veto entries.
    adx_ok = float(tech.get("adx") or 0) >= 16.0
    plus_di = float(tech.get("plus_di") or 0)
    minus_di = float(tech.get("minus_di") or 0)
    volume_ratio = tech.get("volume_ratio")
    volume_ok = volume_ratio is None or float(volume_ratio) >= 0.80
    buy = [ema8[-1] > ema21[-1], plus_di > minus_di, adx_ok, rsi >= 52.0,
           momentum > 0, volume_ok, close > recent_high]
    sell = [ema8[-1] < ema21[-1], minus_di > plus_di, adx_ok, rsi <= 48.0,
            momentum < 0, volume_ok, close < recent_low]
    buy_score, sell_score = sum(map(bool,buy)), sum(map(bool,sell))
    try: hour_local = (datetime.fromisoformat(last["datetime"]).hour + 3) % 24
    except Exception: hour_local = (datetime.now(timezone.utc).hour + 3) % 24
    d = decide(buy_score=buy_score, sell_score=sell_score, rsi=rsi, atr=atr,
        atr_baseline=atr_baseline or atr or 1.0, ema_fast=ema8[-1], ema_slow=ema21[-1],
        close=close, recent_high=recent_high, recent_low=recent_low, momentum=momentum, hour_local=hour_local)
    side=d.side
    guard_reason = None
    # Night sniper window: 19:00-04:29 Palestine local time. Keep 0.01 lot
    # and existing EA risk gate; only tighten the signal stop distance.
    minute_local = hour_local * 60 + datetime.fromisoformat(last["datetime"]).minute
    night_sniper = minute_local >= 19*60 or minute_local < 4*60+30
    # Do not confuse a short pullback with a new trend. The 21/55 EMA regime
    # represents roughly 30-60 minutes of structure on these five-minute bars.
    lookback = min(7, len(ema21)-1)
    slow_slope = ema21[-1] - ema21[-1-lookback] if lookback > 0 else 0.0
    macro_up = slow_slope > 0 and close >= ema55[-1]
    macro_down = slow_slope < 0 and close <= ema55[-1]

    # A first close through support/resistance can be a false breakout. Require
    # the previous closed candle to have broken the older level and the latest
    # candle to hold it before chasing an extended move.
    structure_high = max(r["high"] for r in rows[-8:-2])
    structure_low = min(r["low"] for r in rows[-8:-2])
    buffer = max(0.08, 0.08 * atr)
    held_break_up = rows[-2]["close"] > structure_high + buffer and close > structure_high + buffer
    held_break_down = rows[-2]["close"] < structure_low - buffer and close < structure_low - buffer
    body = max(abs(close-open_), 0.01)
    upper_wick = max(0.0, last["high"]-max(open_, close))
    lower_wick = max(0.0, min(open_, close)-last["low"])

    if side == "BUY":
        if macro_down:
            guard_reason = "buy_is_correction_in_downtrend"
        elif (close >= recent_high-0.15*atr or rsi >= 72.0) and not held_break_up:
            # Fast DEMO scalp exception: a strong 6/7+ impulse may test nearby
            # resistance with a tight stop; weaker setups still wait.
            if not (night_sniper and buy_score >= 6 and momentum > 0 and close > open_ and rsi < 70.0):
                guard_reason = "resistance_not_confirmed"
        elif upper_wick > max(1.25*body, 0.45*atr):
            guard_reason = "upper_wick_rejection"
    elif side == "SELL":
        if macro_up:
            guard_reason = "sell_is_correction_in_uptrend"
        elif (close <= recent_low+0.15*atr or rsi <= 28.0) and not held_break_down:
            # Symmetric fast DEMO scalp exception for a strong 6/7+ sell impulse.
            if not (night_sniper and sell_score >= 6 and momentum < 0 and close < open_ and rsi > 30.0):
                guard_reason = "support_not_confirmed"
        elif lower_wick > max(1.25*body, 0.45*atr):
            guard_reason = "lower_wick_rejection"
    if guard_reason:
        side = None

    # Confirmed support/resistance rejection entries. Do not blindly fade
    # a level: require wick rejection plus momentum/RSI confirmation.
    near_resistance = last["high"] >= recent_high - 0.12 * atr
    near_support = last["low"] <= recent_low + 0.12 * atr
    resistance_rejection = (
        near_resistance and close < open_ and upper_wick >= max(0.35 * atr, 0.75 * body)
        and momentum <= 0 and rsi >= 48.0
    )
    support_rejection = (
        near_support and close > open_ and lower_wick >= max(0.35 * atr, 0.75 * body)
        and momentum >= 0 and rsi <= 52.0
    )
    if side is None and resistance_rejection and not held_break_up:
        side = "SELL"
        guard_reason = None
        d = type(d)("REJECTION_SCALP", "SELL", 6, 0.40, 1.0, 0.90, "resistance_rejection_sniper")
    elif side is None and support_rejection and not held_break_down:
        side = "BUY"
        guard_reason = None
        d = type(d)("REJECTION_SCALP", "BUY", 6, 0.40, 1.0, 0.90, "support_rejection_sniper")

    # User-approved DEMO fast/sniper rule: quick-capture trades only.
    # Any 2 of trend, momentum and RSI are sufficient. This can intentionally
    # take a correction against the larger trend when momentum+RSI agree.
    # MAIN rules and all EA hard DEMO/risk gates remain unchanged.
    primary_buy = int(ema8[-1] > ema21[-1]) + int(momentum > 0) + int(rsi >= 52.0)
    primary_sell = int(ema8[-1] < ema21[-1]) + int(momentum < 0) + int(rsi <= 48.0)
    if side is None and guard_reason not in ("resistance_not_confirmed", "support_not_confirmed", "upper_wick_rejection", "lower_wick_rejection") and max(primary_buy, primary_sell) >= 2:
        if primary_buy > primary_sell and not macro_down:
            side, primary_strength = "BUY", primary_buy
        elif primary_sell > primary_buy and not macro_up:
            side, primary_strength = "SELL", primary_sell
        else:
            side, primary_strength = None, 0
        if side:
            guard_reason = None
            quick_conf = 5 if primary_strength == 2 else 7
            d = type(d)("SNIPER", side, quick_conf, 0.40 if primary_strength == 2 else 0.55,
                        0.0, 1.10 if primary_strength == 2 else 1.25,
                        "fast_primary_2of3" if primary_strength == 2 else "fast_primary_3of3")

    # DEMO rebound entry after an extended selloff. Require exhaustion plus
    # an actual bullish rejection candle; never reverse on RSI alone.
    drop_from_swing = max(r["high"] for r in rows[-12:-1]) - close
    rebound_buy = (
        macro_down
        and rsi <= 30.0
        and drop_from_swing >= max(2.5 * atr, 8.0)
        and close > open_
        and lower_wick >= max(0.30 * atr, 0.75 * body)
        and close > rows[-2]["close"]
    )
    if side is None and rebound_buy:
        side = "BUY"
        guard_reason = None
        d = type(d)("REBOUND", "BUY", 8, 0.60, 0.0, 1.25, "selloff_exhaustion_rebound")

    # Fast DEMO edge override: when the adaptive engine says no_edge but one
    # side has a clear 5/7 vs <=1/7 advantage, allow a confirmed night scalp.
    # Balanced/ambiguous readings (for example 3/7 vs 3/7) remain blocked.
    if side is None and night_sniper and d.reason == "no_edge":
        fast_buy = (
            buy_score >= 5 and sell_score <= 1 and not macro_down
            and close > ema8[-1] and momentum > 0 and close > open_
            and upper_wick <= max(1.25*body, 0.45*atr)
        )
        fast_sell = (
            sell_score >= 5 and buy_score <= 1 and not macro_up
            and close < ema8[-1] and momentum < 0 and close < open_
            and lower_wick <= max(1.25*body, 0.45*atr)
        )
        if fast_buy or fast_sell:
            side = "BUY" if fast_buy else "SELL"
            guard_reason = None
            d = type(d)("NIGHT_SNIPER", side, 7, 0.45, 0.0, 1.25, "fast_5v1_edge")

    # Night-only scout: during the approved 19:00-04:29 window, accept
    # a clean 4/7 micro-edge only when price action confirms it. This raises
    # opportunity count without allowing coin-flip entries.
    if side is None and night_sniper:
        bullish_confirm = close > open_ and close >= rows[-2]["close"] and body >= 0.18*atr
        bearish_confirm = close < open_ and close <= rows[-2]["close"] and body >= 0.18*atr
        scout_buy = (
            buy_score >= 3 and buy_score - sell_score >= 2
            and not macro_down and close > ema8[-1] and momentum > 0
            and bullish_confirm and 42.0 <= rsi < 70.0
            and not ((close >= recent_high - 0.15*atr) and not held_break_up)
            and upper_wick <= max(1.00*body, 0.35*atr)
        )
        scout_sell = (
            sell_score >= 3 and sell_score - buy_score >= 2
            and not macro_up and close < ema8[-1] and momentum < 0
            and bearish_confirm and 30.0 < rsi <= 58.0
            and not ((close <= recent_low + 0.15*atr) and not held_break_down)
            and lower_wick <= max(1.00*body, 0.35*atr)
        )
        if scout_buy or scout_sell:
            side = "BUY" if scout_buy else "SELL"
            guard_reason = None
            scout_score = max(buy_score, sell_score)
            d = type(d)("NIGHT_SNIPER", side, 6 if scout_score <= 4 else 7,
                        0.40 if scout_score == 3 else (0.45 if scout_score == 4 else 0.50), 0.0,
                        1.10 if scout_score <= 4 else 1.20,
                        "night_3of7_fast" if scout_score == 3 else ("night_4of7_micro" if scout_score == 4 else "night_5of7_scout"))

    # Structure-based invalidation stop. For sniper-class trades, a valid
    # setup is not cancelled only because the older swing is too far away.
    # Instead cap the stop by the user-approved strength ladder; the EA still
    # verifies the exact USD loss with OrderCalcProfit before DEMO execution.
    strength = max(buy_score, sell_score)
    sniper_mode = d.mode in ("SNIPER", "NIGHT_SNIPER", "REJECTION_SCALP", "CORRECTION_SCALP")
    sniper_cap = 3.00 if strength <= 4 else (5.00 if strength == 5 else (7.00 if strength == 6 else 10.00))
    if sniper_mode:
        risk_cap = sniper_cap
    else:
        risk_cap = 2.00 if strength <= 4 else (2.60 if strength <= 5 else 3.20)

    structure_pad = max(0.15, 0.10 * atr)
    if side == "BUY":
        structure_stop = recent_low - structure_pad
        structural_risk = close - structure_stop
    elif side == "SELL":
        structure_stop = recent_high + structure_pad
        structural_risk = structure_stop - close
    else:
        structural_risk = 0.0

    if d.mode == "REBOUND" and side == "BUY":
        structural_risk = max(structural_risk, close - last["low"] + max(0.20, 0.10 * atr))

    if side and sniper_mode and structural_risk > 0:
        risk_distance = max(0.80, min(structural_risk, risk_cap))
        if structural_risk > risk_cap:
            guard_reason = None
            d = type(d)(d.mode, side, d.confidence, d.risk_mult, 0.0, d.target_r, "sniper_strength_stop_cap")
    elif side and (structural_risk <= 0 or structural_risk > risk_cap):
        # Non-sniper paths preserve the stricter structural-stop behavior.
        tscore = tech["bull_score"] if side=="BUY" else tech["bear_score"]
        oscore = tech["bear_score"] if side=="BUY" else tech["bull_score"]
        local_stop = (last["low"]-structure_pad) if side=="BUY" else (last["high"]+structure_pad)
        local_risk = (close-local_stop) if side=="BUY" else (local_stop-close)
        strong_original = max(buy_score,sell_score) >= 6
        tech_agrees = tscore >= oscore+2 and (tech.get("adx") or 0) >= 18
        if strong_original and tech_agrees and 0 < local_risk <= risk_cap:
            structural_risk = local_risk
            risk_distance = max(0.80,local_risk)
            guard_reason = None
            d = type(d)("SNIPER",side,6,min(0.55,d.risk_mult or 0.55),0.0,1.0,"technical_medium_local_invalidation")
        else:
            side = None
            guard_reason = "structure_stop_exceeds_risk_cap"
            risk_distance = 0.0
    else:
        risk_distance = max(0.80, structural_risk) if side else 0.0
    if night_sniper and side and d.mode != "REBOUND":
        # Use the same strength ladder through the entire sniper window.
        strength = max(buy_score, sell_score)
        cap = 3.00 if strength <= 4 else (5.00 if strength == 5 else (7.00 if strength == 6 else 10.00))
        risk_distance = min(risk_distance, cap)
        d = type(d)("NIGHT_SNIPER", side, max(7, d.confidence), min(0.60, d.risk_mult), 0.0, 1.25, d.reason)
    if side=="BUY": sl,tp=close-risk_distance,close+risk_distance*d.target_r
    elif side=="SELL": sl,tp=close+risk_distance,close-risk_distance*d.target_r
    else: sl=tp=None
    return {"bar":closed_bar_key(last["datetime"]),"side":side,"score":max(buy_score,sell_score),
        "buy_score":buy_score,"sell_score":sell_score,"checks":{"BUY":buy,"SELL":sell},
        "reference_close":close,"rsi":rsi,"atr":atr,"atr_baseline":atr_baseline,
        "risk_distance":risk_distance,"sl":sl,"tp":tp,"mode":d.mode,
        "confidence":d.confidence,"risk_mult":d.risk_mult,"target_r":d.target_r,
        "reason":guard_reason or d.reason,"held_breakout":held_break_up if d.side=="BUY" else held_break_down,
        "technical":tech,
        "local_buy_risk":max(0.0,close-(last["low"]-structure_pad)),
        "local_sell_risk":max(0.0,(last["high"]+structure_pad)-close)}


def _json_request(url, method="GET", payload=None, headers=None, timeout=10):
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=request_headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"detail": raw[:300]}
        return exc.code, payload


def _parse_yahoo_rows(payload):
    try:
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("market_values_missing")
    rows = []
    opens, highs = quote.get("open") or [], quote.get("high") or []
    lows, closes = quote.get("low") or [], quote.get("close") or []
    for i, ts in enumerate(timestamps):
        try:
            o, h, l, cl = opens[i], highs[i], lows[i], closes[i]
            if None in (o, h, l, cl):
                continue
            rows.append({"datetime": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                         "open": f"{float(o):.5f}", "high": f"{float(h):.5f}",
                         "low": f"{float(l):.5f}", "close": f"{float(cl):.5f}"})
        except (IndexError, TypeError, ValueError):
            continue
    if len(rows) < 31:
        raise RuntimeError("not_enough_market_rows")
    return list(reversed(rows))


def fetch_market_values():
    global _LAST_GOOD_MARKET_ROWS, _LAST_GOOD_MARKET_AT
    """Fetch 5m gold candles with redundant Yahoo endpoints/ranges.

    This remains a directional proxy for DEMO commissioning only. The MT5 EA
    remains the execution and safety gate. Multiple hosts prevent a single
    Yahoo edge returning 503 from putting the worker to sleep.
    """
    errors = []
    nonce = int(time.time() // 30)
    attempts = [
        ("query1.finance.yahoo.com", "5d"),
        ("query2.finance.yahoo.com", "5d"),
        ("query1.finance.yahoo.com", "1mo"),
        ("query2.finance.yahoo.com", "1mo"),
    ]
    for host, range_ in attempts:
        try:
            params = urlencode({"interval": "5m", "range": range_, "_": nonce})
            url = f"https://{host}/v8/finance/chart/{YAHOO_SYMBOL}?{params}"
            status, payload = _json_request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Cache-Control": "no-cache",
            }, timeout=8)
            if status == 200:
                rows = _parse_yahoo_rows(payload)
                _LAST_GOOD_MARKET_ROWS, _LAST_GOOD_MARKET_AT = rows, time.time()
                return rows
            errors.append(f"{host}:{status}")
        except Exception as exc:
            errors.append(f"{host}:{type(exc).__name__}:{exc}")
    # Short provider outages must not blind the DEMO worker. Reuse only a
    # recent successful candle snapshot; never use an old cache for entries.
    cache_age = time.time() - _LAST_GOOD_MARKET_AT
    if _LAST_GOOD_MARKET_ROWS is not None and cache_age <= 360:
        print(f"market_feed_fallback source=recent_cache age={cache_age:.0f}s errors={'|'.join(errors)}", flush=True)
        return _LAST_GOOD_MARKET_ROWS
    raise RuntimeError("market_feed_all_failed:" + "|".join(errors))



def fetch_market_values_tf(interval, ranges):
    errors=[]; nonce=int(time.time()//30)
    for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
        for range_ in ranges:
            try:
                params=urlencode({"interval":interval,"range":range_,"_":nonce})
                status,payload=_json_request(
                    f"https://{host}/v8/finance/chart/{YAHOO_SYMBOL}?{params}",
                    headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)","Cache-Control":"no-cache"},
                    timeout=8)
                if status==200:
                    values=_parse_yahoo_rows(payload)
                    _MTF_CACHE[interval]=(values,time.time())
                    return values
                errors.append(f"{host}:{interval}:{range_}:{status}")
            except Exception as exc:
                errors.append(f"{host}:{interval}:{range_}:{type(exc).__name__}:{exc}")
    cached=_MTF_CACHE.get(interval)
    if cached and time.time()-cached[1] <= 360:
        return cached[0]
    raise RuntimeError("mtf_market_feed_failed:"+"|".join(errors))


def fetch_multitimeframe_values():
    # REAL source of truth: exact JustMarkets MT5 candles relayed by the bridge.
    # H4 is broker-native; aggregation from H1/M15/M5 is forbidden.
    try:
        status,payload=_json_request(f"{BRIDGE_URL}/market",timeout=6)
        if status==200 and payload.get("ok") is True:
            feeds={"5m":payload.get("m5"),"15m":payload.get("m15"),"h4":payload.get("h4")}
            if (isinstance(feeds["5m"],list) and len(feeds["5m"])>=30
                    and isinstance(feeds["15m"],list) and len(feeds["15m"])>=35
                    and isinstance(feeds["h4"],list) and len(feeds["h4"])>=30):
                return feeds
    except Exception as exc:
        print(f"broker_market_feed_unavailable reason={type(exc).__name__}:{exc}",flush=True)
    # Fail closed: REAL never falls back to synthetic or cached H4 for entries.
    raise RuntimeError("broker_native_h4_required")


def adaptive_main_target_r(side, reference, risk_distance, mtf, confidence=0):
    """Choose MAIN profit target from structure instead of a fixed dollar TP.

    The stop remains the M15 structural invalidation. Profit is expressed as
    R-multiple and adapts to setup quality, retest quality and the next H4
    boundary when one is available.
    """
    risk=max(0.01,float(risk_distance or 0))
    ref=float(reference or 0)
    confidence=int(confidence or 0)
    retest=bool(mtf.get("retest_up") if side=="BUY" else mtf.get("retest_down"))
    breakout=bool(mtf.get("break_up") if side=="BUY" else mtf.get("break_down"))

    target_r=1.60
    if breakout:
        target_r=1.90
    if retest:
        target_r=2.20
    if confidence>=9:
        target_r=max(target_r,2.50)
    elif confidence>=8:
        target_r=max(target_r,2.00)

    # Do not blindly target through a nearby H4 barrier. Leave a small buffer
    # before the boundary, but never manufacture a huge target when no boundary
    # is visible in the current map.
    if side=="BUY":
        boundary=float(mtf.get("h4_resistance") or 0)
        room=(boundary-ref) if boundary>ref else 0.0
    else:
        boundary=float(mtf.get("h4_support") or 0)
        room=(ref-boundary) if boundary>0 and boundary<ref else 0.0
    if room>0:
        room_r=(0.88*room)/risk
        if room_r>0:
            target_r=min(target_r,max(0.80,room_r))
    return max(0.80,min(3.00,target_r))


def apply_main_structure(signal, mtf):
    out=dict(signal)
    side=mtf.get("side")
    if side not in ("BUY","SELL"):
        out["mtf"]=mtf
        raw_side=out.get("side")
        score=int(out.get("score") or 0)
        h4=str(mtf.get("h4_bias") or "NEUTRAL").upper()
        m5_ok=(raw_side=="BUY" and mtf.get("m5_confirm_buy")) or (raw_side=="SELL" and mtf.get("m5_confirm_sell"))
        aligned=(raw_side=="BUY" and h4!="DOWN") or (raw_side=="SELL" and h4!="UP")
        tech=out.get("technical") or {}
        m15_open=float(mtf.get("m15_last_open") or 0)
        m15_close=float(mtf.get("m15_last_close") or 0)
        m15_prev=float(mtf.get("m15_prev_close") or 0)
        m15_buy=(m15_close>m15_open and m15_close>=m15_prev)
        m15_sell=(m15_close<m15_open and m15_close<=m15_prev)
        m15_supports=(raw_side=="BUY" and m15_buy) or (raw_side=="SELL" and m15_sell)
        m15_against=(raw_side=="BUY" and m15_sell) or (raw_side=="SELL" and m15_buy)
        # If the older structure gate erased the side, rebuild a medium scalp
        # only from a strong 6/7 M5 signal + M5 confirmation + technical consensus.
        # It uses the latest candle invalidation and keeps the existing 1.60 cap.
        if raw_side not in ("BUY","SELL") and score >= 6:
            synth=None
            if mtf.get("m5_confirm_buy") and int(tech.get("bull_score") or 0) >= int(tech.get("bear_score") or 0)+2:
                synth="BUY"
            elif mtf.get("m5_confirm_sell") and int(tech.get("bear_score") or 0) >= int(tech.get("bull_score") or 0)+2:
                synth="SELL"
            if synth:
                lr=float(out.get("local_buy_risk") if synth=="BUY" else out.get("local_sell_risk") or 0)
                if 0 < lr <= 1.60:
                    out["side"]=synth
                    out["mode"]="SNIPER"
                    out["confidence"]=6
                    out["risk_distance"]=max(0.80,lr)
                    out["target_r"]=1.0
                    out["reason"]="technical_medium_recovered"
                    return out
        # Medium continuation: the strict M15 breakout model is for MAIN entries,
        # but it must not erase a clean 5m setup that agrees with H4/M5.
        # Execute it as the existing SNIPER risk class, not as MAIN.
        if raw_side in ("BUY","SELL") and score >= 5 and m5_ok and aligned and (score>=6 or not m15_against):
            out["mode"]="SNIPER"
            out["confidence"]=6 if score==5 else 7
            out["reason"]="mtf_medium_continuation"
            return out
        # Strong 6/7 M5 confirmation can take a short countertrend bounce/pullback
        # even when H4 points the other way. It remains SNIPER with a smaller
        # target; it is never promoted to MAIN.
        if raw_side in ("BUY","SELL") and score >= 6 and m5_ok:
            out["mode"]="SNIPER"
            out["confidence"]=6
            out["target_r"]=min(float(out.get("target_r") or 1.0),1.0)
            out["reason"]="mtf_countertrend_medium"
            return out
        if raw_side and str(out.get("mode") or "").upper() != "MAIN":
            if score <= 4 and not m15_supports:
                out["side"]=None
                out["reason"]="m15_confirmation_required_for_weak_sniper"
                return out
            if score == 5 and m15_against:
                out["side"]=None
                out["reason"]="m15_against_medium_sniper"
                return out
            out["mode"]="SNIPER"
            return out
        out["side"]=None
        out["reason"]=(signal.get("reason") if raw_side not in ("BUY","SELL")
                       and signal.get("reason") not in (None,"no_edge")
                       else mtf.get("reason","mtf_wait"))
        return out
    out["side"]=side
    out["mode"]="MAIN"
    out["confidence"]=9 if (mtf.get("retest_up") or mtf.get("retest_down")) else 8
    out["reason"]=mtf.get("reason","mtf_structure_entry")
    atr15=float(mtf.get("m15_atr") or 0)
    ref=float(signal.get("reference_close") or 0)
    pad=max(0.20,0.10*atr15)
    if side=="BUY":
        invalidation=min(float(mtf.get("m15_last_low") or ref),
                         float(mtf.get("m15_prev_low") or ref))-pad
        structural=max(0.80,ref-invalidation)
    else:
        invalidation=max(float(mtf.get("m15_last_high") or ref),
                         float(mtf.get("m15_prev_high") or ref))+pad
        structural=max(0.80,invalidation-ref)
    out["risk_distance"]=structural
    out["target_r"]=adaptive_main_target_r(side,ref,structural,mtf,out.get("confidence"))
    out["analysis"]={
        "h4_bias":mtf.get("h4_bias"),
        "m15_structure":out["reason"],
        "m5_confirmation":"bullish_followthrough" if side=="BUY" else "bearish_followthrough",
        "invalidation":"below_m15_candles" if side=="BUY" else "above_m15_candles",
        "h4_support":mtf.get("h4_support"),
        "h4_resistance":mtf.get("h4_resistance"),
        "m15_support":mtf.get("m15_support"),
        "m15_resistance":mtf.get("m15_resistance"),
    }
    out["mtf"]=mtf
    return out


def signal_strength(signal):
    side=signal.get("side")
    selected=(signal.get("checks") or {}).get(side)
    if isinstance(selected,list):
        return sum(bool(x) for x in selected)
    return int(signal.get("score") or max(int(signal.get("buy_score") or 0), int(signal.get("sell_score") or 0)))


def sniper_budget_usd(signal):
    """Requested LIVE sniper stop ladder in USD at the fixed 0.01 lot.

    3-4/7 => $3, 5/7 => $5, 6/7 => $7, 7/7 => $10.
    This is a ceiling, not a forced stop: structure can choose a tighter stop.
    """
    mode=str(signal.get("mode") or "").upper()
    if mode not in ("SNIPER","NIGHT_SNIPER","REJECTION_SCALP","CORRECTION_SCALP"):
        return None
    strength=signal_strength(signal)
    if strength<=4:
        return 3.0
    if strength==5:
        return 5.0
    if strength==6:
        return 7.0
    return 10.0


def sniper_chase_block_reason(signal,last_side,last_score,last_bar):
    side=signal.get("side")
    mode=str(signal.get("mode") or "").upper()
    if side not in ("BUY","SELL") or mode not in ("SNIPER","NIGHT_SNIPER","REJECTION_SCALP","CORRECTION_SCALP"):
        return None
    if side!=last_side or not last_bar:
        return None
    try:
        current=datetime.fromisoformat(str(signal.get("bar")).replace("Z","+00:00"))
        previous=datetime.fromisoformat(str(last_bar).replace("Z","+00:00"))
        seconds=(current-previous).total_seconds()
    except Exception:
        return "same_direction_sniper_chase"
    if seconds<=0 or seconds>5*60+30:
        return None
    strength=signal_strength(signal)
    mtf=signal.get("mtf") or {}
    fresh_break=bool(signal.get("held_breakout")) or (
        side=="BUY" and bool(mtf.get("break_up"))) or (
        side=="SELL" and bool(mtf.get("break_down")))
    if strength>int(last_score or 0) or fresh_break:
        return None
    return "same_direction_sniper_chase"


def same_entry_copies(signal, health):
    """Start with one ticket; a later closed candle can add another entry."""
    risk=max(0.01,float(signal.get("risk_distance") or 0))
    selected=(signal.get("checks") or {}).get(signal.get("side"))
    strength=sum(bool(x) for x in selected) if isinstance(selected,list) else int(signal.get("score") or 0)
    tier=sniper_budget_usd(signal)
    if tier is not None:
        # Sniper uses the requested 3/5/7/10 ladder. The bridge strong budget is
        # still treated as an absolute ceiling, never as the sniper target.
        hard=float(health.get("strong_risk_budget_usd") or 0)
        budget=min(tier,hard) if hard>0 else tier
    else:
        # MAIN stays structural/dynamic and uses the bridge's MAIN safety ceiling.
        budget_field=("strong_risk_budget_usd"
                      if health.get("strong_risk_budget_usd") is not None
                      else "effective_risk_budget_usd")
        budget=float(health.get(budget_field) or 0)
    used=float(health.get("total_position_risk_usd") or health.get("position_risk_usd") or 0)
    available=max(0.0,budget-used)
    return 1 if available+0.01>=risk else 0


def recover_m15_continuation(signal, health):
    """Earlier aligned entry using a closed M15 candle as invalidation.

    The EA calculates the actual broker loss and can still reject the order.
    """
    out=dict(signal)
    if out.get("side") or out.get("reason") != "structure_stop_exceeds_risk_cap":
        return out
    if not health.get("client_state_fresh"):
        return out
    mtf=out.get("mtf") or {}
    choices=[]
    for side in ("BUY","SELL"):
        score=int(out.get("buy_score" if side=="BUY" else "sell_score") or 0)
        opposite=int(out.get("sell_score" if side=="BUY" else "buy_score") or 0)
        checks=(out.get("checks") or {}).get(side) or []
        primary=sum(bool(checks[i]) for i in (0,3,4)) if len(checks)>4 else 0
        aligned=mtf.get("h4_bias")==("UP" if side=="BUY" else "DOWN")
        m5=mtf.get("m5_confirm_buy" if side=="BUY" else "m5_confirm_sell")
        a=float(mtf.get("m15_last_open") or 0)
        c=float(mtf.get("m15_last_close") or 0)
        previous=float(mtf.get("m15_prev_close") or 0)
        m15=(c>a and c>previous) if side=="BUY" else (c<a and c<previous)
        if score>=5 and score-opposite>=2 and primary>=2 and aligned and m5 and m15:
            choices.append((side,score))
    if len(choices)!=1:
        return out
    side,score=choices[0]
    ref=float(out.get("reference_close") or 0)
    pad=max(0.20,0.10*float(mtf.get("m15_atr") or 0))
    if side=="BUY":
        stop=min(float(mtf.get("m15_last_low") or 0),
                 float(mtf.get("m15_prev_low") or 0))-pad
        raw_risk=ref-stop
    else:
        stop=max(float(mtf.get("m15_last_high") or 0),
                 float(mtf.get("m15_prev_high") or 0))+pad
        raw_risk=stop-ref
    risk=max(0.80,raw_risk)
    opposite=int(out.get("sell_score" if side=="BUY" else "buy_score") or 0)
    checks=(out.get("checks") or {}).get(side) or []
    primary=sum(bool(checks[i]) for i in (0,3,4)) if len(checks)>4 else 0
    aligned=mtf.get("h4_bias")==("UP" if side=="BUY" else "DOWN")
    m5=mtf.get("m5_confirm_buy" if side=="BUY" else "m5_confirm_sell")
    a=float(mtf.get("m15_last_open") or 0)
    c=float(mtf.get("m15_last_close") or 0)
    previous=float(mtf.get("m15_prev_close") or 0)
    m15=(c>a and c>previous) if side=="BUY" else (c<a and c<previous)
    breakout=bool(mtf.get("break_up" if side=="BUY" else "break_down"))
    official=(score>=5 and score-opposite>=3 and primary>=2 and aligned and m5 and m15)
    mode="MAIN" if (breakout or official) else "SNIPER"

    if mode=="MAIN":
        # Official trade: use its real M15 invalidation distance; do not squeeze
        # it into a sniper stop. A separate bridge/executor ceiling remains.
        budget=float(health.get("strong_risk_budget_usd") or 0)
    else:
        tier=3.0 if score<=4 else (5.0 if score==5 else (7.0 if score==6 else 10.0))
        hard=float(health.get("strong_risk_budget_usd") or 0)
        budget=min(tier,hard) if hard>0 else tier
    used=float(health.get("total_position_risk_usd") or health.get("position_risk_usd") or 0)
    available=max(0.0,budget-used)
    if raw_risk<=0 or risk>available:
        out["reason"]="m15_stop_exceeds_budget"
        return out
    reason="m15_aligned_official_continuation" if (official and not breakout) else "m15_aligned_continuation"
    confidence=7 if score>=6 else 6
    target_r=(adaptive_main_target_r(side,ref,risk,mtf,confidence)
              if mode=="MAIN" else 1.15)
    out.update(side=side,mode=mode,confidence=confidence,
               risk_distance=risk,target_r=target_r,
               reason=reason)
    if mode=="MAIN":
        out["analysis"]={"h4_bias":mtf.get("h4_bias"),
                         "m15_structure":"aligned_continuation",
                         "m5_confirmation":"directional_followthrough",
                         "invalidation":"m15_candle_extreme",
                         "m15_support":mtf.get("m15_support"),
                         "m15_resistance":mtf.get("m15_resistance")}
    return out


def recover_strong_structural_entry(signal, health):
    """Use a real candle invalidation for a strong setup when the fixed cap is too tight.

    The EA independently checks actual broker entry, spread, and planned USD loss.
    This is only a DEMO candidate; it cannot grant itself extra risk budget.
    """
    out = dict(signal)
    if out.get("side") or out.get("reason") != "structure_stop_exceeds_risk_cap":
        return out
    if not health.get("client_state_fresh"):
        return out
    mtf = out.get("mtf") or {}
    h4 = str(mtf.get("h4_bias") or "NEUTRAL").upper()
    tech = out.get("technical") or {}
    choices = []
    for side in ("BUY", "SELL"):
        score = int(out.get("buy_score" if side == "BUY" else "sell_score") or 0)
        opposite = int(out.get("sell_score" if side == "BUY" else "buy_score") or 0)
        confirms = mtf.get("m5_confirm_buy" if side == "BUY" else "m5_confirm_sell")
        aligned = h4 == ("UP" if side == "BUY" else "DOWN")
        breakout = mtf.get("break_up" if side == "BUY" else "break_down")
        agreement = (int(tech.get("bull_score" if side == "BUY" else "bear_score") or 0)
                     - int(tech.get("bear_score" if side == "BUY" else "bull_score") or 0))
        if score >= 6 and score - opposite >= 3 and confirms and agreement >= 2 and (aligned or breakout):
            choices.append((side, score))
    if len(choices) != 1:
        return out
    side, score = choices[0]
    raw_risk = float(out.get("local_buy_risk" if side == "BUY" else "local_sell_risk") or 0)
    risk = max(0.80, raw_risk)
    budget = float(health.get("strong_risk_budget_usd") or health.get("effective_risk_budget_usd") or 0)
    used = float(health.get("total_position_risk_usd") or health.get("position_risk_usd") or 0)
    available = max(0.0, budget - used)
    if raw_risk <= 0 or risk > available or risk > 15.0:
        out["reason"] = "strong_signal_stop_exceeds_budget"
        return out
    out.update(side=side, mode="SNIPER", confidence=7 if score == 7 else 6,
               risk_distance=risk, target_r=1.0,
               reason="strong_signal_candle_invalidation")
    return out

def bridge_health():
    # Railway public routing can briefly return 503 during edge/container handoff.
    # Retry health only; this never bypasses state/risk gates or publishes a trade.
    last_error = None
    for attempt in range(3):
        try:
            status, payload = _json_request(f"{BRIDGE_URL}/health")
            if status == 200:
                return payload
            last_error = RuntimeError(f"bridge_health_http_{status}")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(2)
    raise RuntimeError(f"bridge_health_unavailable:{last_error}")


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


def publish_signal(signal, spot_override=None, copy_index=1):
    side = signal["side"]
    # Prefer the fresh MT5 broker price already authenticated through /state.
    # External spot remains fallback only.
    spot = float(spot_override or 0)
    if spot <= 0:
        spot = fetch_spot_price()
    risk_distance = float(signal["risk_distance"])
    if side == "BUY":
        sl = spot - risk_distance
        tp = spot + risk_distance * float(signal.get("target_r", 1.5))
    else:
        sl = spot + risk_distance
        tp = spot - risk_distance * float(signal.get("target_r", 1.5))
    trade_mode = "MAIN" if str(signal.get("mode") or "").upper() == "MAIN" else "SNIPER"
    payload = {
        "mode": "DEMO",
        "trade_mode": trade_mode,
        "key": f"auto:{signal['bar'].replace(' ','T').replace(':','').replace('-','')}:{trade_mode}:{side}:C{copy_index}:S{sum(bool(x) for x in signal['checks'][side])}",
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


def execution_block_reason(health):
    """Legacy EA polling proves connectivity, never position/risk telemetry.

    Compatibility is explicit and applies only to clients that have never sent
    state. If a reporting client stops sending state, keep blocking entries.
    Every command still passes the installed EA's DEMO and local safety gates.
    """
    if health.get("mode") != "DEMO":
        return "bridge_not_demo"
    if not health.get("enabled"):
        return "bridge_disabled"
    if not health.get("client_state_fresh"):
        if not ALLOW_STALE_MT5_STATE or health.get("client_last_seen_age") is not None:
            return "mt5_state_stale"
        if not health.get("client_poll_fresh"):
            return "mt5_disconnected"
    if int(health.get("pending", 0) or 0) >= 4:
        return "pending_command_limit"
    return None

def run_forever():
    validate_config()
    print(
        f"bridge_signal_worker_started version={WORKER_VERSION} symbol={SYMBOL} interval=5m "
        f"adaptive_modes=SNIPER,MAIN,REBOUND,NIGHT_SNIPER,WAIT volume={VOLUME:.2f} max_publish_per_hour={MAX_PUBLISH_PER_HOUR} "
        f"allow_stale_mt5_state={ALLOW_STALE_MT5_STATE}",
        flush=True,
    )
    last_bar = None
    last_sniper_side = None
    last_sniper_score = 0
    last_sniper_bar = None
    publishes = deque()

    while True:
        try:
            now = time.time()
            while publishes and now - publishes[0] >= 3600:
                publishes.popleft()

            health = bridge_health()
            block_reason = execution_block_reason(health)
            if block_reason:
                print(f"bridge_signal_skip reason={block_reason}", flush=True)
                time.sleep(POLL_SECONDS)
                continue
            if not health.get("client_state_fresh"):
                print("bridge_signal_legacy mt5_poll=fresh state=unavailable local_ea_safety_required=true", flush=True)
            if MAX_PUBLISH_PER_HOUR > 0 and len(publishes) >= MAX_PUBLISH_PER_HOUR:
                print("bridge_signal_skip reason=hourly_publish_cap", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            feeds = fetch_multitimeframe_values()
            try:
                validate_market_feed_freshness(feeds)
            except RuntimeError as exc:
                if str(exc).startswith(("stale_market_data:", "market_clock_ahead:")):
                    print(f"bridge_signal_skip reason={exc}", flush=True)
                    time.sleep(POLL_SECONDS)
                    continue
                raise
            signal = compute_signal(feeds["5m"])
            mtf = analyze_structure(normalize_rows(feeds["5m"]), normalize_rows(feeds["15m"]), normalize_rows(feeds["h4"]))
            signal = apply_main_structure(signal, mtf)
            signal = recover_m15_continuation(signal, health)
            signal = recover_strong_structural_entry(signal, health)
            if signal["bar"] == last_bar:
                time.sleep(POLL_SECONDS)
                continue
            last_bar = signal["bar"]

            if not signal["side"]:
                print(
                    f"bridge_signal_wait bar={signal['bar']} buy={signal['buy_score']}/7 "
                    f"sell={signal['sell_score']}/7 close={signal['reference_close']:.2f} rsi={signal['rsi']:.1f} reason={signal.get('reason')} "
                    f"h4={signal.get('mtf',{}).get('h4_bias')} "
                    f"m5buy={signal.get('mtf',{}).get('m5_confirm_buy')} m5sell={signal.get('mtf',{}).get('m5_confirm_sell')} "
                    f"m15S={signal.get('mtf',{}).get('m15_support')} m15R={signal.get('mtf',{}).get('m15_resistance')} "
                    f"local_buy_risk={signal.get('local_buy_risk')} local_sell_risk={signal.get('local_sell_risk')} "
                    f"risk_budget={health.get('effective_risk_budget_usd')} strong_risk_budget={health.get('strong_risk_budget_usd')} "
                    f"position_risk={health.get('total_position_risk_usd',health.get('position_risk_usd'))}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            chase_reason=sniper_chase_block_reason(
                signal,last_sniper_side,last_sniper_score,last_sniper_bar)
            if chase_reason:
                print(f"bridge_signal_skip reason={chase_reason} side={signal.get('side')} score={signal_strength(signal)}", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            mt5_spot = float(health.get("price") or 0) if health.get("client_state_fresh") else 0.0
            copies = same_entry_copies(signal, health)
            if copies <= 0:
                print(f"bridge_signal_skip reason=aggregate_risk_budget budget={health.get('effective_risk_budget_usd')} "
                      f"used={health.get('total_position_risk_usd',health.get('position_risk_usd'))} "
                      f"required={signal.get('risk_distance')} side={signal.get('side')}", flush=True)
                time.sleep(POLL_SECONDS)
                continue
            slots=MAX_PUBLISH_PER_HOUR-len(publishes) if MAX_PUBLISH_PER_HOUR>0 else copies
            for copy_index in range(1, min(copies,slots) + 1):
                status, response, key = publish_signal(signal, mt5_spot, copy_index)
                if status == 201 and response.get("ok") is True:
                    if MAX_PUBLISH_PER_HOUR > 0:
                        publishes.append(time.time())
                    if str(signal.get("mode") or "").upper() != "MAIN":
                        last_sniper_side=signal.get("side")
                        last_sniper_score=signal_strength(signal)
                        last_sniper_bar=signal.get("bar")
                    print(
                        f"bridge_signal_published key={key} side={signal['side']} "
                        f"mode={signal.get('mode')} confidence={signal.get('confidence')} copies={copies} "
                        f"reference_proxy={signal['reference_close']:.2f} risk_distance={signal['risk_distance']:.2f} "
                        f"h4={signal.get('mtf',{}).get('h4_bias')} m15S={signal.get('mtf',{}).get('m15_support')} "
                        f"m15R={signal.get('mtf',{}).get('m15_resistance')}",
                        flush=True,
                    )
                else:
                    print(f"bridge_signal_publish_rejected status={status} reason={response.get('reason','unknown')}", flush=True)
                    break
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            print(f"bridge_signal_error type={type(exc).__name__} detail={exc}", flush=True)
        except Exception as exc:
            print(f"bridge_signal_error type={type(exc).__name__} detail={exc}", flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    run_forever()