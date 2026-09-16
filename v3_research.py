"""Experimental V3 signal lab.

This module is intentionally isolated from bot.py and is not used by the live bot.
It wraps the current analyzer and adds research-only controls:
1) reject forced/best-available bias as a trade candidate,
2) tag/filter by liquid trading session,
3) classify ATR volatility regime,
4) attach slow global macro context and test only strong conflicts,
5) map causal support/resistance, break/retest/failure, corrections and structural stops.

Nothing in this file sends Telegram alerts or broker orders.
"""
from zoneinfo import ZoneInfo

from engine import analyze, atr
from market import resample
from v3_global_data import macro_alignment
from v3_price_action import analyze_price_action

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
    """Return ATR percentile regime from closed 15-minute bars."""
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


def research_gate(base, session, vol, macro=None, price_action=None):
    """Return a research veto reason or None.

    V3 never creates a trade when the baseline has none. It filters already-strict
    candidates and tests whether better location/invalidation improves outcomes.
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
    if price_action and price_action.get("available"):
        breakout = price_action.get("breakout") or {}
        if breakout.get("state") == "FAILED_BREAK":
            return "v3_failed_breakout_against_entry"
        correction = price_action.get("correction") or {}
        if correction.get("triggered") and correction.get("strength") == "STRONG":
            return "v3_strong_correction_against_entry"
        risk = price_action.get("risk_plan") or {}
        if not risk.get("valid"):
            return "v3_" + str(risk.get("reason") or "risk_plan_invalid")
    return None


def _zone_summary(zone):
    if not zone:
        return None
    return {
        "low": zone.get("low"), "center": zone.get("center"), "high": zone.get("high"),
        "touches": zone.get("touches"), "score": zone.get("score"),
    }


def analyze_v3(bars, now, macro=None):
    """Research candidate built on top of the current live analyzer.

    All added fields are observable at decision time. Strength labels describe
    completed rules, not calibrated probabilities. A valid structural risk plan
    replaces the baseline ATR-only SL/TP in V3 paper trades so it can be tested
    side-by-side; the live bot remains unchanged.
    """
    base = analyze(bars, now)
    result = dict(base)
    session = session_label(now)
    vol = volatility_regime(bars)
    alignment = macro_alignment(base.get("side"), macro)
    price_action = analyze_price_action(bars, base)

    levels = price_action.get("levels") or {}
    breakout = price_action.get("breakout") or {}
    correction = price_action.get("correction") or {}
    risk = price_action.get("risk_plan") or {}
    result["v3"] = {
        "session": session,
        "volatility_regime": vol["label"],
        "volatility_percentile": vol["percentile"],
        "macro_alignment": alignment,
        "macro_score": macro.get("gold_macro_score") if macro else None,
        "macro_source": macro.get("source") if macro else None,
        "macro_max_staleness_days": macro.get("max_staleness_days") if macro else None,
        "nearest_support": _zone_summary(levels.get("nearest_support")),
        "nearest_resistance": _zone_summary(levels.get("nearest_resistance")),
        "breakout_state": breakout.get("state"),
        "critical_level": _zone_summary(breakout.get("level")),
        "correction": correction,
        "structural_risk": risk,
        "research_only": True,
    }

    veto = research_gate(base, session, vol, macro, price_action)
    if veto:
        result.update(side="WAIT", reason=veto)
        return result

    if result.get("side") in ("BUY", "SELL") and risk.get("valid"):
        result.update(
            sl=risk["stop"], tp1=risk["tp1"], tp2=risk["tp2"],
            reason="v3_structural_entry",
        )
    return result
