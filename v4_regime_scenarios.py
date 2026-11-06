"""Deterministic, no-lookahead market regime and scenario intelligence for V4.

Consumes completed candles only; never invents future outcomes or probabilities.
This module provides advisory hypotheses, not an automatic order.
"""
import math


def analyze_regime(bars, *, atr_window=14, trend_window=20):
    """Classify trend, range or high volatility using closed OHLC candles."""
    if not bars or len(bars) < max(atr_window + 1, trend_window):
        return {"regime": "UNKNOWN", "reason": "insufficient_closed_bars", "actionable": False}
    try:
        rows = []
        for bar in bars:
            h = float(getattr(bar, "high", bar["high"] if isinstance(bar, dict) else None))
            l = float(getattr(bar, "low", bar["low"] if isinstance(bar, dict) else None))
            c = float(getattr(bar, "close", bar["close"] if isinstance(bar, dict) else None))
            if not all(math.isfinite(x) and x > 0 for x in (h, l, c)) or l > c or c > h:
                raise ValueError("invalid OHLC")
            rows.append((h, l, c))
        trs = [max(rows[i][0] - rows[i][1], abs(rows[i][0] - rows[i-1][2]),
                   abs(rows[i][1] - rows[i-1][2])) for i in range(1, len(rows))]
        atr = sum(trs[-atr_window:]) / atr_window
        if atr <= 0:
            return {"regime": "UNKNOWN", "reason": "zero_volatility", "actionable": False}
        closes = [x[2] for x in rows[-trend_window:]]
        net = closes[-1] - closes[0]
        path = sum(abs(b-a) for a, b in zip(closes, closes[1:]))
        efficiency = abs(net) / path if path else 0
        previous_atr = (sum(trs[-2*atr_window:-atr_window]) / atr_window
                        if len(trs) >= 2*atr_window else None)
        if previous_atr and atr > 2.0 * previous_atr:
            regime = "HIGH_VOLATILITY"
        elif efficiency >= 0.55 and abs(net) >= 2 * atr:
            regime = "UPTREND" if net > 0 else "DOWNTREND"
        else:
            regime = "RANGE"
        return {"regime": regime, "atr": round(atr, 6),
                "efficiency": round(efficiency, 4), "actionable": regime != "HIGH_VOLATILITY",
                "reason": "closed_candle_observation"}
    except (TypeError, ValueError, AttributeError, ZeroDivisionError):
        return {"regime": "UNKNOWN", "reason": "invalid_closed_bars", "actionable": False}


def scenario_hypotheses(regime, *, support, resistance, last_price):
    """Return falsifiable scenarios; levels are supplied by the caller, not guessed."""
    try:
        support, resistance, price = map(float, (support, resistance, last_price))
        if not all(math.isfinite(x) and x > 0 for x in (support, resistance, price)) or support >= resistance:
            return ()
    except (TypeError, ValueError):
        return ()
    kind = regime.get("regime", "UNKNOWN")
    if kind in ("UNKNOWN", "HIGH_VOLATILITY"):
        return ()
    return (
        {"scenario": "BULLISH_BREAKOUT", "trigger": resistance,
         "confirmation": "closed_candle_above_resistance_and_retest",
         "invalidation": support, "preferred": kind == "UPTREND"},
        {"scenario": "BEARISH_BREAKDOWN", "trigger": support,
         "confirmation": "closed_candle_below_support_and_retest",
         "invalidation": resistance, "preferred": kind == "DOWNTREND"},
        {"scenario": "RANGE_REJECTION", "lower_bound": support,
         "upper_bound": resistance, "confirmation": "rejection_candle_inside_range",
         "invalidation": "confirmed_close_outside_range", "preferred": kind == "RANGE"},
    )
