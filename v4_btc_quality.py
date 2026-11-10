"""BTC signal-quality checks: spot microstructure, liquidity, session and risk.

All factors are observational; never submit orders or invent missing broker data.
"""
from datetime import timezone
import math
from statistics import median

from market import DataError

UTC = timezone.utc


def btc_session(now):
    """UTC session label (research metadata, not a promised best trading time)."""
    hour = now.astimezone(UTC).hour
    if now.weekday() >= 5:
        return "WEEKEND"
    if 12 <= hour < 21:
        return "US"
    if 7 <= hour < 16:
        return "EU"
    return "ASIA"


def detect_liquidity(m15, side, atr15):
    """Use already completed bars; reference highs/lows exclude trigger bars."""
    if len(m15) < 15:
        raise DataError("btc_liquidity_history_short")
    reference = m15[-14:-2]
    high = max(b.high for b in reference)
    low = min(b.low for b in reference)
    previous, last = m15[-2:]
    buffer = max(atr15 * .07, high * .00005)
    if side == "BUY":
        fake = last.high > high + buffer and last.close < high
        sweep = last.low < low - buffer and last.close > low
        breakout = previous.close > high + buffer and last.close > high and last.low <= high + buffer
        pullback = last.low <= low + .35 * atr15 and last.close > low and last.close > last.open
    else:
        fake = last.low < low - buffer and last.close > low
        sweep = last.high > high + buffer and last.close < high
        breakout = previous.close < low - buffer and last.close < low and last.high >= low - buffer
        pullback = last.high >= high - .35 * atr15 and last.close < high and last.close < last.open
    return {
        "fake_breakout": bool(fake),
        "liquidity_sweep": bool(sweep),
        "confirmed_retest": bool(breakout),
        "support": low,
        "resistance": high,
        "pullback": bool(pullback),
        "context_ok": bool(sweep or breakout or pullback),
    }


def m5_sniper(m5, side):
    if len(m5) < 12:
        raise DataError("btc_m5_history_short")
    recent = m5[-4:]
    last = recent[-1]
    previous = recent[-2]
    midpoint = (previous.high + previous.low) / 2
    body = abs(last.close - last.open)
    span = max(last.high - last.low, 1e-9)
    if side == "BUY":
        return (last.close > last.open and last.close >= midpoint
                and last.close >= last.low + .55 * span and body >= .20 * span)
    return (last.close < last.open and last.close <= midpoint
            and last.close <= last.high - .55 * span and body >= .20 * span)


def volume_confirmation(volumes, session):
    """Require true Coinbase traded-volume data, not synthesized tick volume."""
    if volumes is None or len(volumes) < 22:
        return {"ok": False, "ratio": None, "reason": "volume_unavailable"}
    try:
        valid = [float(v) for v in volumes[-22:]]
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "ratio": None, "reason": "volume_invalid"}
    if any(not math.isfinite(v) or v < 0 for v in valid):
        return {"ok": False, "ratio": None, "reason": "volume_invalid"}
    baseline = median(valid[-21:-1])
    if baseline <= 0:
        return {"ok": False, "ratio": None, "reason": "volume_baseline_zero"}
    ratio = valid[-1] / baseline
    # Weekend liquidity may differ; use a stricter volume gate.
    return {"ok": ratio >= (1.15 if session == "WEEKEND" else .8),
            "ratio": round(ratio, 3), "reason": "ok" if ratio >= (1.15 if session == "WEEKEND" else .8) else "low_volume"}


def check_book(book, side):
    """REST level-2 snapshot only, not an integrated streaming order-flow feed."""
    if not isinstance(book, dict) or "bids" not in book or "asks" not in book:
        raise DataError("btc_book_unavailable")
    def top(rows):
        values = []
        for row in rows[:15]:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                raise DataError("btc_book_invalid")
            price, qty = float(row[0]), float(row[1])
            if not all(math.isfinite(v) and v > 0 for v in (price, qty)):
                raise DataError("btc_book_invalid")
            values.append((price, qty))
        if not values:
            raise DataError("btc_book_empty")
        return values
    bids, asks = top(book["bids"]), top(book["asks"])
    bid, ask = max(p for p, _ in bids), min(p for p, _ in asks)
    if ask <= bid:
        raise DataError("btc_crossed_book")
    midpoint = (bid + ask) / 2
    spread_bps = (ask - bid) / midpoint * 10000
    bid_notional = sum(p * q for p, q in bids)
    ask_notional = sum(p * q for p, q in asks)
    imbalance = (bid_notional - ask_notional) / (bid_notional + ask_notional)
    return {
        "spread_bps": round(spread_bps, 3),
        "imbalance": round(imbalance, 4),
        "bid": bid, "ask": ask,
        "ok": spread_bps <= 6 and
            ((imbalance >= -.35) if side == "BUY" else (imbalance <= .35)),
    }


def derivatives_context(payload, side, now):
    """Binance BTCUSDT perpetual evidence is a separate market from Coinbase spot.
    Missing/blocked source is explicitly unavailable, not zero funding/OI.
    """
    if not isinstance(payload, dict) or not payload.get("available"):
        return {"available": False, "risk": "UNVERIFIED"}
    try:
        funding = float(payload["funding"])
        oi = float(payload["open_interest"])
        previous_oi = float(payload["previous_open_interest"])
        stamp = float(payload["timestamp"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"available": False, "risk": "UNVERIFIED"}
    if (not all(math.isfinite(x) for x in (funding, oi, previous_oi, stamp))
            or oi <= 0 or previous_oi <= 0
            or not 0 <= now.timestamp() - stamp < 25 * 60):
        return {"available": False, "risk": "UNVERIFIED"}
    oi_change = (oi - previous_oi) / previous_oi
    crowded = ((side == "BUY" and funding > .0008) or
               (side == "SELL" and funding < -.0008)) and oi_change > .02
    return {"available": True, "risk": "CROWDED" if crowded else "NORMAL",
            "funding": round(funding, 6), "oi_change": round(oi_change, 4)}


def dynamic_risk(price, side, volatility, spread_bps, session):
    """Volatility-adjusted spot reference levels; fees and CFD basis unknown."""
    if not all(math.isfinite(x) and x > 0 for x in (price, volatility)):
        raise DataError("btc_bad_risk_inputs")
    ratio = volatility / price
    if ratio > .035:
        return {"status": "WAIT", "reason": "btc_extreme_volatility"}
    multiple = 1.75 if ratio > .012 else (1.55 if session == "WEEKEND" else 1.35)
    risk_distance = volatility * multiple
    spread_cost = price * max(0, spread_bps) / 10000
    if risk_distance <= 2 * spread_cost:
        return {"status": "WAIT", "reason": "btc_cost_exceeds_risk"}
    side_sign = 1 if side == "BUY" else -1
    stop = price - side_sign * risk_distance
    tp1 = price + side_sign * risk_distance * 1.8
    tp2 = price + side_sign * risk_distance * 2.8
    if min(stop, tp1, tp2) <= 0:
        return {"status": "WAIT", "reason": "btc_invalid_levels"}
    rr_after_spread = (1.8 * risk_distance - spread_cost) / (risk_distance + spread_cost)
    if rr_after_spread < 1.55:
        return {"status": "WAIT", "reason": "btc_spread_adjusted_rr_low"}
    return {"status": "OK", "sl": stop, "tp1": tp1, "tp2": tp2,
            "rr_reference": round(rr_after_spread, 2), "volatility_regime": "HIGH" if ratio > .012 else "NORMAL",
            "sl_distance": risk_distance}


def quality_gate(now, side, price, m5, m15, atr15, volumes, book, derivatives):
    """Combines all approved filters; missing critical data = WAIT_DATA."""
    session = btc_session(now)
    liquidity = detect_liquidity(m15, side, atr15)
    if liquidity["fake_breakout"]:
        return {"status": "WAIT", "reason": "btc_false_breakout", "liquidity": liquidity}
    if not liquidity["context_ok"]:
        return {"status": "WAIT", "reason": "btc_liquidity_not_confirmed", "liquidity": liquidity}
    if not m5_sniper(m5, side):
        return {"status": "WAIT", "reason": "btc_sniper_not_confirmed", "liquidity": liquidity}
    volume = volume_confirmation(volumes, session)
    if not volume["ok"]:
        return {"status": "WAIT_DATA" if volume["ratio"] is None else "WAIT",
                "reason": volume["reason"], "volume": volume}
    market = check_book(book, side)
    if not market["ok"]:
        return {"status": "WAIT", "reason": "btc_book_spread_or_imbalance", "book": market}
    d = derivatives_context(derivatives, side, now)
    if d["risk"] == "CROWDED":
        return {"status": "WAIT", "reason": "btc_crowded_derivatives", "derivatives": d}
    risk = dynamic_risk(price, side, atr15, market["spread_bps"], session)
    if risk["status"] != "OK":
        return risk
    return {
        "status": "OK", "liquidity": liquidity, "volume": volume, "book": market,
        "derivatives": d, "risk": risk, "session": session,
        "trade_timeframe": "M15", "timing": "M5",
        "broker_spread_verified": False,
    }
