"""Experimental V3 signal lab.

This module is intentionally isolated from bot.py and is not used by the live bot.
It wraps the current analyzer and adds three research-only controls:
1) reject forced/best-available bias as a trade candidate,
2) tag and optionally filter by liquid trading session,
3) classify ATR volatility regime and block only extreme regimes.

Nothing in this file sends Telegram alerts or broker orders.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from engine import analyze, atr
from market import resample

TOKYO = ZoneInfo("Asia/Tokyo")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")


def _inside(dt, start_hour, end_hour):
    local = dt.astimezone(dt.tzinfo)
    value = local.hour + local.minute / 60
    return start_hour <= value < end_hour


def session_label(now):
    """DST-aware coarse liquidity session label for research stratification."""
    tokyo = now.astimezone(TOKYO)
    london = now.astimezone(LONDON)
    new_york = now.astimezone(NEW_YORK)

    in_tokyo = 8 <= tokyo.hour < 16
    in_london = 8 <= london.hour < 17
    in_new_york = 8 <= new_york.hour < 17

    if in_london and in_new_york:
        return "LONDON_NEW_YORK_OVERLAP"
    if in_new_york:
        return "NEW_YORK"
    if in_london:
        return "LONDON"
    if in_tokyo:
        return "ASIA"
    return "OTHER"


def volatility_regime(bars, lookback=96):
    """Return ATR percentile regime from closed 15-minute bars.

    Percentile is computed only from information available at the decision time.
    It is descriptive research metadata, not a calibrated probability.
    """
    m15 = resample(bars, 15)
    if len(m15) < 30:
        return {"label": "UNAVAILABLE", "percentile": None, "atr": None}

    values = []
    start = max(15, len(m15) - lookback)
    for end in range(start, len(m15) + 1):
        try:
            values.append(atr(m15[:end]))
        except ValueError:
            continue
    if not values:
        return {"label": "UNAVAILABLE", "percentile": None, "atr": None}

    current = values[-1]
    rank = sum(v <= current for v in values) / len(values)
    percentile = round(rank * 100, 1)
    if percentile >= 95:
        label = "EXTREME"
    elif percentile >= 75:
        label = "HIGH"
    elif percentile <= 20:
        label = "LOW"
    else:
        label = "NORMAL"
    return {"label": label, "percentile": percentile, "atr": current}


def analyze_v3(bars, now):
    """Research candidate built on top of the current live analyzer.

    This function never invents a side when the live model only has a forced bias.
    Session and volatility metadata are attached for later out-of-sample comparison.
    Only OTHER session and EXTREME volatility are research vetoes in this first pass.
    """
    base = analyze(bars, now)
    result = dict(base)
    session = session_label(now)
    vol = volatility_regime(bars)
    result["v3"] = {
        "session": session,
        "volatility_regime": vol["label"],
        "volatility_percentile": vol["percentile"],
        "research_only": True,
    }

    if base.get("forced") or base.get("reason") == "best_available_bias":
        result.update(side="WAIT", reason="v3_forced_bias_rejected")
        return result
    if session == "OTHER":
        result.update(side="WAIT", reason="v3_outside_core_session")
        return result
    if vol["label"] == "EXTREME":
        result.update(side="WAIT", reason="v3_extreme_volatility")
        return result
    return result
