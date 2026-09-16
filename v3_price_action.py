"""Causal price-action research features for Laith Bot V3.

The goal is to turn subjective chart language (support, resistance, correction,
failed breakout, structural stop) into deterministic rules that can be tested.
Nothing here is a claim that a level *must* hold.  Levels are zones inferred only
from already-closed bars; pivots require right-hand confirmation so historical
backtests do not use future information.
"""
from math import isfinite

from engine import atr, ema
from market import resample


def confirmed_pivots(bars, left=2, right=2):
    """Return causally confirmed swing highs/lows.

    A pivot at index i is not knowable until ``right`` later bars have closed.
    This function therefore never treats the newest ``right`` bars as pivots.
    """
    if len(bars) < left + right + 1:
        return []
    out = []
    for i in range(left, len(bars) - right):
        window = bars[i - left:i + right + 1]
        bar = bars[i]
        other_highs = [b.high for j, b in enumerate(window) if j != left]
        other_lows = [b.low for j, b in enumerate(window) if j != left]
        if bar.high > max(other_highs):
            out.append({"kind": "HIGH", "price": bar.high, "index": i, "time": bar.end.isoformat()})
        if bar.low < min(other_lows):
            out.append({"kind": "LOW", "price": bar.low, "index": i, "time": bar.end.isoformat()})
    return out


def _cluster(points, width):
    zones = []
    for point in points:
        price = point["price"]
        match = None
        for zone in zones:
            if abs(price - zone["center"]) <= width:
                match = zone
                break
        if match is None:
            zones.append({
                "center": price,
                "touches": 1,
                "weight": point.get("weight", 1.0),
                "last_rank": point.get("rank", 0),
                "high_touches": int(point["kind"] == "HIGH"),
                "low_touches": int(point["kind"] == "LOW"),
            })
        else:
            total = match["weight"] + point.get("weight", 1.0)
            match["center"] = (match["center"] * match["weight"] + price * point.get("weight", 1.0)) / total
            match["weight"] = total
            match["touches"] += 1
            match["last_rank"] = max(match["last_rank"], point.get("rank", 0))
            match["high_touches"] += int(point["kind"] == "HIGH")
            match["low_touches"] += int(point["kind"] == "LOW")
    for zone in zones:
        zone["low"] = zone["center"] - width
        zone["high"] = zone["center"] + width
        # Touches matter most; higher-timeframe points enter with weight=2.
        zone["score"] = round(zone["touches"] + 0.5 * zone["weight"], 2)
    return zones


def structural_levels(bars, price, atr_value=None):
    """Build support/resistance zones from confirmed M15 and H1 pivots."""
    m15, h1 = resample(bars, 15), resample(bars, 60)
    if not m15:
        return {"supports": [], "resistances": [], "nearest_support": None, "nearest_resistance": None,
                "atr": atr_value, "zone_width": None}
    if atr_value is None:
        try:
            atr_value = atr(m15)
        except ValueError:
            atr_value = max(m15[-1].high - m15[-1].low, 0.01)
    if not isfinite(atr_value) or atr_value <= 0:
        atr_value = max(m15[-1].high - m15[-1].low, 0.01)
    width = max(0.18 * atr_value, 0.01)

    points = []
    p15 = confirmed_pivots(m15)
    p60 = confirmed_pivots(h1)
    for rank, point in enumerate(p15[-40:], 1):
        points.append(dict(point, weight=1.0, rank=rank))
    for rank, point in enumerate(p60[-24:], 1):
        points.append(dict(point, weight=2.0, rank=rank + 100))
    zones = _cluster(points, width)
    zones.sort(key=lambda z: z["center"])

    supports = [z for z in zones if z["center"] <= price]
    resistances = [z for z in zones if z["center"] >= price]
    supports.sort(key=lambda z: price - z["center"])
    resistances.sort(key=lambda z: z["center"] - price)
    return {
        "supports": supports[:6],
        "resistances": resistances[:6],
        "nearest_support": supports[0] if supports else None,
        "nearest_resistance": resistances[0] if resistances else None,
        "atr": atr_value,
        "zone_width": width,
    }


def breakout_state(bars, side, levels):
    """Classify the nearest opposing level: hold, confirmed break, retest or failure."""
    m15 = resample(bars, 15)
    av = levels.get("atr") or 0.0
    if len(m15) < 5 or av <= 0 or side not in ("BUY", "SELL"):
        return {"state": "UNAVAILABLE", "level": None}
    level = levels.get("nearest_resistance" if side == "BUY" else "nearest_support")
    if not level:
        return {"state": "OPEN_SPACE", "level": None}
    buffer = 0.10 * av
    recent = m15[-5:]
    last = recent[-1]
    if side == "BUY":
        confirmed = all(b.close > level["high"] + buffer for b in m15[-2:])
        had_break = any(b.close > level["high"] + buffer for b in recent[:-1])
        retest = had_break and last.low <= level["high"] + buffer and last.close > level["center"]
        failed = (last.high > level["high"] + buffer and last.close < level["center"])
    else:
        confirmed = all(b.close < level["low"] - buffer for b in m15[-2:])
        had_break = any(b.close < level["low"] - buffer for b in recent[:-1])
        retest = had_break and last.high >= level["low"] - buffer and last.close < level["center"]
        failed = (last.low < level["low"] - buffer and last.close > level["center"])
    state = "FAILED_BREAK" if failed else "RETEST_HELD" if retest else "CONFIRMED_BREAK" if confirmed else "LEVEL_INTACT"
    return {"state": state, "level": level, "buffer": buffer}


def _latest_impulse(m15, trend):
    pivots = confirmed_pivots(m15)
    if trend == "BUY":
        highs = [p for p in pivots if p["kind"] == "HIGH"]
        if not highs:
            return None
        end = highs[-1]
        lows = [p for p in pivots if p["kind"] == "LOW" and p["index"] < end["index"]]
        if not lows:
            return None
        start = lows[-1]
    elif trend == "SELL":
        lows = [p for p in pivots if p["kind"] == "LOW"]
        if not lows:
            return None
        end = lows[-1]
        highs = [p for p in pivots if p["kind"] == "HIGH" and p["index"] < end["index"]]
        if not highs:
            return None
        start = highs[-1]
    else:
        return None
    move = abs(end["price"] - start["price"])
    if move <= 0:
        return None
    return {"start": start, "end": end, "size": move}


def correction_map(bars, base, levels):
    """Estimate where a counter-trend correction can start and where it may reach.

    Strength is rule-completion (weak/medium/strong), not a success probability.
    Retracement marks are recorded as research reference points, not as magical
    Fibonacci claims; structural zones remain the primary targets.
    """
    m15 = resample(bars, 15)
    context = base.get("context") or {}
    trend = context.get("trend")
    av = levels.get("atr") or base.get("atr")
    if len(m15) < 10 or trend not in ("BUY", "SELL") or not av:
        return {"direction": None, "strength": "UNAVAILABLE", "triggered": False}
    impulse = _latest_impulse(m15, trend)
    if not impulse:
        return {"direction": "DOWN" if trend == "BUY" else "UP", "strength": "UNAVAILABLE", "triggered": False}

    start_price = impulse["end"]["price"]
    width = max(0.20 * av, 0.01)
    start_zone = {"low": start_price - width, "high": start_price + width, "center": start_price}
    start = impulse["start"]["price"]
    end = impulse["end"]["price"]
    if trend == "BUY":
        retr = {
            "r38": end - 0.382 * (end - start),
            "r50": end - 0.500 * (end - start),
            "r62": end - 0.618 * (end - start),
        }
        supports = levels.get("supports", [])
        structural = [z for z in supports if z["center"] < start_price]
        t1 = structural[0]["center"] if structural else retr["r38"]
        t2 = structural[1]["center"] if len(structural) > 1 else retr["r62"]
        invalidation = start_price + 0.25 * av
        counter_candle = m15[-1].close < m15[-1].open
        wick_reject = m15[-1].high >= start_zone["low"] and m15[-1].close < start_zone["center"]
        rsi_pressure = (base.get("rsi") or 0) >= 65
        structure_pressure = context.get("local_structure") == "SELL"
        near_start = abs(base.get("price", m15[-1].close) - start_price) <= 0.55 * av
    else:
        retr = {
            "r38": end + 0.382 * (start - end),
            "r50": end + 0.500 * (start - end),
            "r62": end + 0.618 * (start - end),
        }
        resistances = levels.get("resistances", [])
        structural = [z for z in resistances if z["center"] > start_price]
        t1 = structural[0]["center"] if structural else retr["r38"]
        t2 = structural[1]["center"] if len(structural) > 1 else retr["r62"]
        invalidation = start_price - 0.25 * av
        counter_candle = m15[-1].close > m15[-1].open
        wick_reject = m15[-1].low <= start_zone["high"] and m15[-1].close > start_zone["center"]
        rsi_pressure = (base.get("rsi") or 100) <= 35
        structure_pressure = context.get("local_structure") == "BUY"
        near_start = abs(base.get("price", m15[-1].close) - start_price) <= 0.55 * av

    score = 0
    score += 2 if context.get("phase") == "pullback" else 0
    score += int(counter_candle)
    score += int(wick_reject)
    score += int(rsi_pressure)
    score += int(structure_pressure)
    score += int(near_start)
    strength = "STRONG" if score >= 4 else "MEDIUM" if score >= 2 else "WEAK"
    triggered = score >= 3 and (counter_candle or wick_reject)
    return {
        "direction": "DOWN" if trend == "BUY" else "UP",
        "trend": trend,
        "strength": strength,
        "score": score,
        "triggered": triggered,
        "start_zone": start_zone,
        "target1": t1,
        "target2": t2,
        "invalidation": invalidation,
        "retracement_grid": retr,
        "impulse_start": start,
        "impulse_end": end,
    }


def structural_risk_plan(base, levels, breakout):
    """Create a paper-only stop/target plan from structural invalidation + ATR buffer."""
    side = base.get("side")
    entry = base.get("price")
    av = levels.get("atr") or base.get("atr")
    if side not in ("BUY", "SELL") or not entry or not av or av <= 0:
        return {"valid": False, "reason": "unavailable"}
    direction = 1 if side == "BUY" else -1
    buffer = 0.18 * av
    if side == "BUY":
        candidates = [z for z in levels.get("supports", []) if z["center"] < entry]
        structural = candidates[0] if candidates else None
        raw_stop = structural["low"] - buffer if structural else entry - 1.10 * av
        stop = min(raw_stop, entry - 0.65 * av)
        opposing = levels.get("nearest_resistance")
        room = (opposing["low"] - entry) if opposing else None
    else:
        candidates = [z for z in levels.get("resistances", []) if z["center"] > entry]
        structural = candidates[0] if candidates else None
        raw_stop = structural["high"] + buffer if structural else entry + 1.10 * av
        stop = max(raw_stop, entry + 0.65 * av)
        opposing = levels.get("nearest_support")
        room = (entry - opposing["high"]) if opposing else None
    risk = abs(entry - stop)
    if risk > 2.20 * av:
        return {"valid": False, "reason": "structural_stop_too_wide", "risk_atr": risk / av,
                "stop": stop, "source_level": structural}
    room_r = (room / risk) if room is not None else None
    if (room_r is not None and room_r < 1.15
            and breakout.get("state") not in ("CONFIRMED_BREAK", "RETEST_HELD")):
        return {"valid": False, "reason": "opposing_structure_too_close", "risk_atr": risk / av,
                "room_r": room_r, "stop": stop, "source_level": structural,
                "opposing_level": opposing}
    tp1 = entry + direction * 1.40 * risk
    tp2 = entry + direction * 2.20 * risk
    return {
        "valid": True,
        "reason": "structural_invalidation",
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "risk_atr": risk / av,
        "room_r": room_r,
        "source_level": structural,
        "opposing_level": opposing,
    }


def analyze_price_action(bars, base):
    """Return the complete research map used by V3 and its reports."""
    price = base.get("price")
    if not price:
        return {"available": False}
    levels = structural_levels(bars, price, base.get("atr"))
    breakout = breakout_state(bars, base.get("side"), levels)
    correction = correction_map(bars, base, levels)
    risk = structural_risk_plan(base, levels, breakout)
    return {
        "available": True,
        "levels": levels,
        "breakout": breakout,
        "correction": correction,
        "risk_plan": risk,
    }
