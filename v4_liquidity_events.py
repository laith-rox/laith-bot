"""Advisory-only V4 liquidity sweep and false-breakout detector.

Uses completed OHLC candles only. No orders, future bars or invented confidence.
"""
import math


def detect_liquidity_event(bars, *, lookback=12):
    """Inspect last closed candle against prior completed candle range.

    Returns sweep rejection, confirmed breakout, or NONE. A close outside the
    range is not considered a retest confirmation.
    """
    if not bars or len(bars) < lookback + 1 or lookback < 3:
        return {"event": "UNKNOWN", "reason": "insufficient_closed_bars"}
    try:
        def ohlc(bar):
            if isinstance(bar, dict):
                return tuple(float(bar[k]) for k in ("open", "high", "low", "close"))
            return tuple(float(getattr(bar, k)) for k in ("open", "high", "low", "close"))
        rows = [ohlc(b) for b in bars[-lookback-1:]]
        if any(not all(math.isfinite(x) and x > 0 for x in r) or
               r[2] > min(r[0], r[3]) or max(r[0], r[3]) > r[1] for r in rows):
            raise ValueError("invalid OHLC")
        upper = max(r[1] for r in rows[:-1])
        lower = min(r[2] for r in rows[:-1])
        _, high, low, close = rows[-1]
        if high > upper and close <= upper and close >= lower:
            event, side = "BUY_SIDE_SWEEP_REJECTION", "BEARISH"
        elif low < lower and close >= lower and close <= upper:
            event, side = "SELL_SIDE_SWEEP_REJECTION", "BULLISH"
        elif close > upper:
            event, side = "BREAKOUT_ABOVE_RANGE", "BULLISH"
        elif close < lower:
            event, side = "BREAKDOWN_BELOW_RANGE", "BEARISH"
        else:
            event, side = "NONE", "NEUTRAL"
        return {"event": event, "bias": side, "range_high": upper,
                "range_low": lower, "last_close": close,
                "retest_confirmed": False, "manual_only": True}
    except (TypeError, ValueError, AttributeError, KeyError):
        return {"event": "UNKNOWN", "reason": "invalid_closed_bars"}
