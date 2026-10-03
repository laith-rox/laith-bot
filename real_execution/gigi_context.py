"""Fuse Gigi shadow-analysis layers into an explainable context score.

This is not a win probability and it never sends an order. It only summarizes
whether regime, intermarket and macro context support or contradict the
technical setup.
"""
from __future__ import annotations


def evaluate(side, regime, intermarket, macro):
    side=str(side or "WAIT").upper()
    regime=regime or {}
    intermarket=intermarket or {}
    macro=macro or {}

    score=0
    reasons=[]

    name=str(regime.get("name") or "UNKNOWN").upper()
    h4=str(regime.get("h4_bias") or "NEUTRAL").upper()
    effort=str(regime.get("effort_result") or "UNKNOWN").upper()

    if side=="BUY":
        if h4=="UP":
            score+=2; reasons.append("h4_regime_supports_buy")
        elif h4=="DOWN":
            score-=2; reasons.append("h4_regime_conflicts_buy")
    elif side=="SELL":
        if h4=="DOWN":
            score+=2; reasons.append("h4_regime_supports_sell")
        elif h4=="UP":
            score-=2; reasons.append("h4_regime_conflicts_sell")

    if name in ("VOLATILE_TRANSITION","TRANSITION"):
        score-=1
        reasons.append("transition_regime")
    elif name=="RANGE":
        reasons.append("range_regime")

    if effort=="ABSORPTION":
        reasons.append("effort_result_absorption")
    elif effort=="EXPANSION_CONFIRMED":
        score+=1
        reasons.append("effort_result_expansion")

    inter_bias=str(intermarket.get("bias") or "NEUTRAL").upper()
    if side=="BUY":
        if inter_bias=="BULLISH_GOLD":
            score+=1; reasons.append("intermarket_supports_buy")
        elif inter_bias=="BEARISH_GOLD":
            score-=1; reasons.append("intermarket_conflicts_buy")
    elif side=="SELL":
        if inter_bias=="BEARISH_GOLD":
            score+=1; reasons.append("intermarket_supports_sell")
        elif inter_bias=="BULLISH_GOLD":
            score-=1; reasons.append("intermarket_conflicts_sell")

    macro_regime=str(macro.get("regime") or "UNKNOWN").upper()
    if macro_regime=="HIGH_IMPACT_WINDOW":
        score-=2
        reasons.append("high_impact_usd_window")
        market_state="EVENT_DRIVEN"
    elif macro_regime=="MEDIUM_IMPACT_WINDOW":
        score-=1
        reasons.append("medium_impact_usd_window")
        market_state="EVENT_AWARE"
    elif macro_regime=="UNKNOWN":
        reasons.append("macro_unknown")
        market_state="UNKNOWN_MACRO"
    else:
        market_state="NORMAL"

    if score>=3:
        alignment="STRONG_SUPPORT"
    elif score>=1:
        alignment="SUPPORT"
    elif score<=-3:
        alignment="STRONG_CONFLICT"
    elif score<=-1:
        alignment="CONFLICT"
    else:
        alignment="MIXED"

    return {
        "alignment": alignment,
        "score": int(score),
        "market_state": market_state,
        "reasons": reasons,
        "note": "alignment_score_not_probability",
    }
