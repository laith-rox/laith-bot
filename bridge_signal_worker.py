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
WORKER_VERSION = "bridge-tech-pattern-v26"


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
            "datetime": str(item.get("datetime", "")).replace(".", "-", 2),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "tick_volume": float(item.get("tick_volume") or 0),
        })
    return rows


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
    buy = [ema8[-1] > ema21[-1], close > ema8[-1], ema8[-1] > ema8[-2], rsi >= 52.0, momentum > 0, close > open_, close > recent_high]
    sell = [ema8[-1] < ema21[-1], close < ema8[-1], ema8[-1] < ema8[-2], rsi <= 48.0, momentum < 0, close < open_, close < recent_low]
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
        if primary_buy > primary_sell:
            side, primary_strength = "BUY", primary_buy
        elif primary_sell > primary_buy:
            side, primary_strength = "SELL", primary_sell
        else:
            side, primary_strength = None, 0
        if side:
            guard_reason = None
            is_correction = (side == "BUY" and macro_down) or (side == "SELL" and macro_up)
            quick_conf = 5 if primary_strength == 2 else 7
            # A confirmed correction is its own quick trade: follow the correction,
            # take a smaller target and leave the main trend logic independent.
            if is_correction:
                d = type(d)("CORRECTION_SCALP", side, quick_conf, 0.35 if primary_strength == 2 else 0.45,
                            0.0, 0.75 if primary_strength == 2 else 0.90,
                            "correction_primary_2of3" if primary_strength == 2 else "correction_primary_3of3")
            else:
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

    # Structure-based invalidation stop. SELL stops belong above the recent
    # resistance zone; BUY stops belong below recent support. If the structural
    # stop needs more room than the existing mode cap, reject the setup instead
    # of widening risk. This preserves the existing DEMO risk ceiling.
    strength = max(buy_score, sell_score)
    if d.mode == "CORRECTION_SCALP":
        risk_cap = 1.00 if strength <= 4 else 1.30
    elif d.mode in ("SNIPER", "NIGHT_SNIPER"):
        risk_cap = 1.10 if strength <= 3 else (1.35 if strength <= 4 else 1.60)
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

    if side and (structural_risk <= 0 or structural_risk > risk_cap):
        # Medium setup rescue: when the candle/indicator layer agrees with the
        # original signal, use the latest candle as the scalp invalidation
        # instead of rejecting a good entry because an older swing is too far.
        # The existing risk cap is never widened.
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
        # Night trades are short-lived scalps. Keep the tighter stop requested:
        # 1.50 for opportunistic 5/7 scouts, up to 2.00 for stronger setups.
        strength = max(buy_score, sell_score)
        cap = 1.00 if strength == 3 else (1.20 if strength == 4 else (1.50 if strength == 5 else 2.00))
        risk_distance = min(risk_distance, cap)
        d = type(d)("NIGHT_SNIPER", side, max(7, d.confidence), min(0.60, d.risk_mult), 0.0, 1.25, d.reason)
    if side=="BUY": sl,tp=close-risk_distance,close+risk_distance*d.target_r
    elif side=="SELL": sl,tp=close+risk_distance,close-risk_distance*d.target_r
    else: sl=tp=None
    return {"bar":last["datetime"],"side":side,"score":max(buy_score,sell_score),
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
    # Primary source: the exact JustMarkets MT5 DEMO candles relayed by the EA.
    # This keeps support/resistance aligned with the chart that actually executes.
    try:
        status,payload=_json_request(f"{BRIDGE_URL}/market",timeout=6)
        if status==200 and payload.get("ok") is True:
            feeds={"5m":payload.get("m5"),"15m":payload.get("m15"),"1h":payload.get("h1")}
            if all(isinstance(v,list) and len(v)>=30 for v in feeds.values()):
                return feeds
    except Exception as exc:
        print(f"broker_market_feed_fallback reason={type(exc).__name__}:{exc}",flush=True)
    # Directional proxy fallback only if broker relay is temporarily unavailable.
    return {
        "5m": fetch_market_values_tf("5m",("5d","1mo")),
        "15m": fetch_market_values_tf("15m",("5d","1mo")),
        "1h": fetch_market_values_tf("1h",("1mo","3mo")),
    }


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
        if raw_side in ("BUY","SELL") and score >= 5 and m5_ok and aligned:
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
            out["mode"]="SNIPER"
            return out
        out["side"]=None; out["reason"]=mtf.get("reason","mtf_wait")
        return out
    out["side"]=side
    out["mode"]="MAIN"
    out["confidence"]=9 if (mtf.get("retest_up") or mtf.get("retest_down")) else 8
    out["reason"]=mtf.get("reason","mtf_structure_entry")
    atr15=float(mtf.get("m15_atr") or 0)
    ref=float(signal.get("reference_close") or 0)
    if side=="BUY":
        invalidation=float(mtf.get("m15_resistance") or ref)-max(0.20,0.20*atr15)
        structural=max(0.80,ref-invalidation)
    else:
        invalidation=float(mtf.get("m15_support") or ref)+max(0.20,0.20*atr15)
        structural=max(0.80,invalidation-ref)
    out["risk_distance"]=structural
    out["target_r"]=2.0
    out["analysis"]={
        "h4_bias":mtf.get("h4_bias"),
        "m15_structure":out["reason"],
        "m5_confirmation":"bullish_followthrough" if side=="BUY" else "bearish_followthrough",
        "invalidation":"below_structure_zone" if side=="BUY" else "above_structure_zone",
        "h4_support":mtf.get("h4_support"),
        "h4_resistance":mtf.get("h4_resistance"),
        "m15_support":mtf.get("m15_support"),
        "m15_resistance":mtf.get("m15_resistance"),
    }
    out["mtf"]=mtf
    return out


def same_entry_copies(signal, health):
    """Allow multiple 0.01 tickets only inside the unchanged S5 aggregate budget."""
    risk=max(0.01,float(signal.get("risk_distance") or 0))
    full=float(health.get("effective_risk_budget_usd") or 0)
    budget=0.50*full
    used=float(health.get("total_position_risk_usd") or health.get("position_risk_usd") or 0)
    available=max(0.0,budget-used)
    return max(1,min(4,int(available//risk))) if available+0.01>=risk else 0

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
        "key": f"auto:{signal['bar'].replace(' ','T').replace(':','').replace('-','')}:{trade_mode}:{side}:C{copy_index}",
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
            signal = compute_signal(feeds["5m"])
            mtf = analyze_structure(normalize_rows(feeds["5m"]), normalize_rows(feeds["15m"]), normalize_rows(feeds["1h"]))
            signal = apply_main_structure(signal, mtf)
            if signal["bar"] == last_bar:
                time.sleep(POLL_SECONDS)
                continue
            last_bar = signal["bar"]

            if not signal["side"]:
                print(
                    f"bridge_signal_wait bar={signal['bar']} buy={signal['buy_score']}/7 "
                    f"sell={signal['sell_score']}/7 rsi={signal['rsi']:.1f} reason={signal.get('reason')} "
                    f"h4={signal.get('mtf',{}).get('h4_bias')} "
                    f"m5buy={signal.get('mtf',{}).get('m5_confirm_buy')} m5sell={signal.get('mtf',{}).get('m5_confirm_sell')} "
                    f"m15S={signal.get('mtf',{}).get('m15_support')} m15R={signal.get('mtf',{}).get('m15_resistance')}",
                    flush=True,
                )
                time.sleep(POLL_SECONDS)
                continue

            mt5_spot = float(health.get("price") or 0) if health.get("client_state_fresh") else 0.0
            copies = same_entry_copies(signal, health)
            if copies <= 0:
                print("bridge_signal_skip reason=aggregate_risk_budget", flush=True)
                time.sleep(POLL_SECONDS)
                continue
            for copy_index in range(1, copies + 1):
                status, response, key = publish_signal(signal, mt5_spot, copy_index)
                if status == 201 and response.get("ok") is True:
                    if MAX_PUBLISH_PER_HOUR > 0:
                        publishes.append(time.time())
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
