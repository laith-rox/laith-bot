"""Experimental V3 signal lab.

This module is intentionally isolated from bot.py and is not used by the live bot.
It wraps the current analyzer and adds research-only controls:
1) reject forced/best-available bias as a trade candidate,
2) tag and optionally filter by liquid trading session,
3) classify ATR volatility regime,
4) attach slow-moving global macro context and test only strong conflicts.

Nothing in this file sends Telegram alerts or broker orders.
"""
from zoneinfo import ZoneInfo

from engine import analyze, atr
from market import resample
from v3_global_data import macro_alignment

TOKYO = ZoneInfo("Asia/Tokyo")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")


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


def research_gate(base, session, vol, macro=None):
    """Return a research veto reason or None.

    The first V3 generation is intentionally conservative.  It does not add a
    new trade when the baseline has none.  It only rejects weak/poor-context
    candidates so the experiment tests whether selectivity improves results.
    """
    if base.get("forced") or base.get("reason") == "best_available_bias":
        return "v3_forced_bias_rejected"
    if base.get("side") not in ("BUY", "SELL"):
        return None
    if session == "OTHER":
        return "v3_outside_core_session"
    if vol.get("label") == "EXTREME":
        return "v3_extreme_volatility"
    alignment = macro_alignment(base.get("side"), macro)
    if alignment == "STRONG_CONFLICT":
        return "v3_strong_macro_conflict"
    return None


def analyze_v3(bars, now, macro=None):
    """Research candidate built on top of the current live analyzer.

    Session, volatility and macro metadata are attached for later out-of-sample
    comparison.  Macro context is a filter only when it is strongly opposed to
    an already-strict technical setup; missing macro data never invents a trade.
    """
    base = analyze(bars, now)
    result = dict(base)
    session = session_label(now)
    vol = volatility_regime(bars)
    alignment = macro_alignment(base.get("side"), macro)
    result["v3"] = {
        "session": session,
        "volatility_regime": vol["label"],
        "volatility_percentile": vol["percentile"],
        "macro_alignment": alignment,
        "macro_score": macro.get("gold_macro_score") if macro else None,
        "macro_max_staleness_days": macro.get("max_staleness_days") if macro else None,
        "research_only": True,
    }

    veto = research_gate(base, session, vol, macro)
    if veto:
        result.update(side="WAIT", reason=veto)
    return result
