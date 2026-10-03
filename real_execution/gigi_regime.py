"""Pure market-regime context for Gigi REAL analysis.

This module never sends orders. It classifies broker-native closed candles so
the signal layer can explain whether gold is trending, ranging, expanding, or
showing effort/result divergence (absorption).
"""
from __future__ import annotations

from statistics import median


def _ema(values, period):
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1.0 - alpha) * out[-1])
    return out


def _atr(rows, period=14):
    if len(rows) < 2:
        return 0.0
    trs = []
    start = max(1, len(rows) - period)
    for i in range(start, len(rows)):
        prev = float(rows[i-1]["close"])
        high = float(rows[i]["high"])
        low = float(rows[i]["low"])
        trs.append(max(high-low, abs(high-prev), abs(low-prev)))
    return sum(trs) / len(trs) if trs else 0.0


def _atr_history(rows, period=14, samples=12):
    out = []
    start = max(period + 2, len(rows) - samples)
    for end in range(start, len(rows) + 1):
        value = _atr(rows[:end], period)
        if value > 0:
            out.append(value)
    return out


def _effort_result(m5):
    if len(m5) < 12:
        return "UNKNOWN"
    latest = m5[-1]
    vols = [float(r.get("tick_volume") or 0) for r in m5[-12:-1]]
    ranges = [max(0.0, float(r["high"]) - float(r["low"])) for r in m5[-12:-1]]
    med_vol = median([v for v in vols if v > 0]) if any(v > 0 for v in vols) else 0.0
    med_range = median([x for x in ranges if x > 0]) if any(x > 0 for x in ranges) else 0.0
    latest_vol = float(latest.get("tick_volume") or 0)
    latest_range = max(0.0, float(latest["high"]) - float(latest["low"]))
    if med_vol <= 0 or med_range <= 0:
        return "NEUTRAL"
    effort = latest_vol / med_vol
    result = latest_range / med_range
    if effort >= 1.35 and result <= 0.70:
        return "ABSORPTION"
    if effort >= 1.20 and result >= 1.20:
        return "EXPANSION_CONFIRMED"
    if effort <= 0.75 and result >= 1.25:
        return "THIN_MOVE"
    return "BALANCED"


def classify(m5, m15, h4):
    if len(m5) < 30 or len(m15) < 35 or len(h4) < 30:
        return {
            "name": "UNKNOWN",
            "volatility": "UNKNOWN",
            "h4_bias": "NEUTRAL",
            "atr_ratio": 0.0,
            "effort_result": "UNKNOWN",
        }

    h4_close = [float(r["close"]) for r in h4]
    e20 = _ema(h4_close, 20)
    e50 = _ema(h4_close, 50)
    slope = e20[-1] - e20[-3]
    h4_atr = max(_atr(h4, 14), 1e-9)
    separation = abs(e20[-1] - e50[-1]) / h4_atr
    slope_norm = slope / h4_atr

    atr15 = max(_atr(m15, 14), 1e-9)
    hist = _atr_history(m15, 14, 12)
    baseline = (sum(hist[:-1]) / len(hist[:-1])) if len(hist) > 1 else atr15
    atr_ratio = atr15 / max(baseline, 1e-9)

    if atr_ratio >= 1.35:
        volatility = "EXPANDING"
    elif atr_ratio <= 0.75:
        volatility = "COMPRESSED"
    else:
        volatility = "NORMAL"

    if separation < 0.30 and abs(slope_norm) < 0.10:
        name = "RANGE"
        h4_bias = "NEUTRAL"
    elif e20[-1] > e50[-1] and slope > 0:
        name = "TREND_UP"
        h4_bias = "UP"
    elif e20[-1] < e50[-1] and slope < 0:
        name = "TREND_DOWN"
        h4_bias = "DOWN"
    else:
        name = "TRANSITION"
        h4_bias = "NEUTRAL"

    if volatility == "EXPANDING" and name in ("TREND_UP", "TREND_DOWN"):
        name = "TREND_EXPANSION"
    elif volatility == "EXPANDING" and name in ("RANGE", "TRANSITION"):
        name = "VOLATILE_TRANSITION"

    return {
        "name": name,
        "volatility": volatility,
        "h4_bias": h4_bias,
        "atr_ratio": round(float(atr_ratio), 3),
        "h4_separation_atr": round(float(separation), 3),
        "h4_slope_atr": round(float(slope_norm), 3),
        "effort_result": _effort_result(m5),
    }
