"""Deterministic signal and observational trade lifecycle; no broker orders."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import math

from market import resample, require_fresh, DataError


def ema(values, period):
    if not values:
        raise ValueError("empty_indicator_input")
    k = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * k + result[-1] * (1 - k))
    return result


def rsi(values, period=14):
    if len(values) <= period:
        raise ValueError("insufficient_rsi_history")
    changes = [b - a for a, b in zip(values, values[1:])]
    gains = [max(d, 0) for d in changes]
    losses = [max(-d, 0) for d in changes]
    gain, loss = sum(gains[:period]) / period, sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        gain = (gain * (period - 1) + g) / period
        loss = (loss * (period - 1) + l) / period
    return 100 - 100 / (1 + gain / loss) if loss else (100.0 if gain else 50.0)


def atr(bars, period=14):
    if len(bars) <= period:
        raise ValueError("insufficient_atr_history")
    ranges = [max(b.high - b.low, abs(b.high - prev.close), abs(b.low - prev.close))
              for prev, b in zip(bars, bars[1:])]
    value = sum(ranges[:period]) / period
    for item in ranges[period:]:
        value = (value * (period - 1) + item) / period
    return value


def macd(values):
    line = [a - b for a, b in zip(ema(values, 12), ema(values, 26))]
    return line[-1] - ema(line, 9)[-1]


def analyze(bars, now):
    require_fresh(bars, now, 120)
    m15, h1 = resample(bars, 15), resample(bars, 60)
    if len(m15) < 220 or len(h1) < 100:
        raise DataError("market_insufficient_closed_history")
    require_fresh(m15, now, 1200)
    require_fresh(h1, now, 3900)
    result = {"side": "WAIT", "bar": m15[-1].end.isoformat(),
              "price_time": bars[-1].end.isoformat(), "reason": "conditions_not_aligned"}
    if any((b.start - a.start).total_seconds() != 300 for a, b in zip(bars[-4:], bars[-3:])):
        return dict(result, reason="recent_data_gap")
    c15, c1h = [b.close for b in m15], [b.close for b in h1]
    price = bars[-1].close
    e20, e50 = ema(c15, 20)[-1], ema(c15, 50)[-1]
    h20, h50 = ema(c1h, 20)[-1], ema(c1h, 50)[-1]
    rv, mh, av = rsi(c15), macd(c15), atr(m15)
    if not math.isfinite(av) or av <= 0:
        return dict(result, reason="invalid_volatility")
    not_extended = abs(price - e20) <= 1.5 * av
    buy = [e20 > e50, h20 > h50, mh > 0, 51 <= rv <= 69,
           price > e20, m15[-1].close > m15[-1].open, not_extended]
    sell = [e20 < e50, h20 < h50, mh < 0, 31 <= rv <= 49,
            price < e20, m15[-1].close < m15[-1].open, not_extended]
    # Trend, RSI, price position and anti-chasing guard cannot be outvoted.
    core = (0, 1, 3, 4, 6)
    side = "BUY" if sum(buy) >= 6 and all(buy[i] for i in core) else (
        "SELL" if sum(sell) >= 6 and all(sell[i] for i in core) else "WAIT")
    result.update(side=side, price=price, atr=av, rsi=rv, buy=sum(buy), sell=sum(sell))
    if side != "WAIT":
        direction = 1 if side == "BUY" else -1
        result.update(sl=price - direction * 1.4 * av, tp1=price + direction * 1.8 * av,
                      tp2=price + direction * 2.6 * av, reason="entry_conditions_met")
    elif not not_extended:
        result["reason"] = "price_extended"
    elif not 31 <= rv <= 69:
        result["reason"] = "rsi_extreme"
    return result


def make_trade(decision, now):
    if decision["side"] not in ("BUY", "SELL"):
        raise ValueError("cannot_open_wait_signal")
    key = "XAU/USD:" + decision["bar"] + ":" + decision["side"]
    return {"id": hashlib.sha256(key.encode()).hexdigest()[:12],
            "side": decision["side"], "entry": decision["price"],
            "initial_sl": decision["sl"], "stop": decision["sl"],
            "tp1": decision["tp1"], "tp2": decision["tp2"], "tp1_hit": False,
            "created": now.timestamp(), "announced": None, "last_end": None,
            "bar": decision["bar"], "status": "pending", "outcome": None,
            "data_gap": False, "delivery_uncertain": False, "r": None}


def advance_trade(original, bars):
    """Replay each closed 5m candle once. Ambiguous OHLC ordering is not a win.

    TP1 is a milestone; its protective stop is effective from the NEXT candle.
    A bar spanning delivery uses only its close, avoiding pre-delivery extremes.
    """
    trade, events = deepcopy(original), []
    if trade["status"] not in ("active", "uncertain_delivery") or trade["announced"] is None:
        return trade, events
    direction = 1 if trade["side"] == "BUY" else -1
    risk = abs(trade["entry"] - trade["initial_sl"])
    for bar in bars:
        end, start = bar.end.timestamp(), bar.start.timestamp()
        if end <= (trade["last_end"] or trade["announced"]):
            continue
        if trade["last_end"] is not None and start > trade["last_end"]:
            trade["data_gap"] = True
        elif trade["last_end"] is None and start > trade["announced"] + 300:
            trade["data_gap"] = True
        partial = start < trade["announced"]
        low, high, opening = (bar.close, bar.close, bar.close) if partial else (bar.low, bar.high, bar.open)
        stop_hit = low <= trade["stop"] if direction == 1 else high >= trade["stop"]
        first_hit = high >= trade["tp1"] if direction == 1 else low <= trade["tp1"]
        final_hit = high >= trade["tp2"] if direction == 1 else low <= trade["tp2"]
        stop_gap = opening <= trade["stop"] if direction == 1 else opening >= trade["stop"]
        target_gap = opening >= trade["tp2"] if direction == 1 else opening <= trade["tp2"]
        outcome, exit_price = None, None
        if stop_gap:
            outcome, exit_price = "PROTECTED_STOP" if trade["tp1_hit"] else "STOP", opening
        elif target_gap:
            outcome, exit_price = "TP2", trade["tp2"]
        elif stop_hit and (final_hit or (first_hit and not trade["tp1_hit"])):
            outcome = "AMBIGUOUS"
        elif stop_hit:
            outcome, exit_price = "PROTECTED_STOP" if trade["tp1_hit"] else "STOP", trade["stop"]
        elif final_hit:
            outcome, exit_price = "TP2", trade["tp2"]
        elif first_hit and not trade["tp1_hit"]:
            trade["tp1_hit"] = True
            trade["stop"] = trade["entry"]
            events.append({"kind": "tp1", "time": end})
        trade["last_end"] = end
        if outcome:
            trade.update(status="closed", outcome=outcome, closed=end, exit=exit_price)
            if exit_price is not None and not trade["data_gap"] and not trade["delivery_uncertain"]:
                trade["r"] = direction * (exit_price - trade["entry"]) / risk
            events.append({"kind": "exit", "time": end})
            break
    return trade, events
