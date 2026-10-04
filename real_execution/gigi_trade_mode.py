"""Gigi trade-mode selector for shadow analysis.

Chooses the *requested analytical mode* from evidence quality:
MAIN = official/structural idea, SNIPER = quick tactical idea, NO_TRADE = evidence
is not good enough. This module never places or authorizes an order.
"""
from __future__ import annotations


def choose(signal=None, context=None, crowding=None, volatility=None, macro=None):
    signal=signal or {}
    context=context or {}
    crowding=crowding or {}
    volatility=volatility or {}
    macro=macro or {}

    side=str(signal.get("side") or "").upper()
    checks=(signal.get("checks") or {}).get(side, [])
    strength=sum(bool(x) for x in checks)
    confidence=int(signal.get("confidence") or 0)
    regime=signal.get("regime") or {}
    h4_bias=str(regime.get("h4_bias") or "NEUTRAL").upper()
    market_regime=str(regime.get("name") or "UNKNOWN").upper()
    alignment=str(context.get("alignment") or "NEUTRAL").upper()
    crowding_risk=str(crowding.get("dominant_risk") or "BALANCED").upper()
    vol_state=str(volatility.get("state") or "UNKNOWN").upper()
    macro_regime=str(macro.get("regime") or "CLEAR").upper()
    session=str(signal.get("session") or "UNKNOWN").upper()

    reasons=[]
    if side not in ("BUY","SELL"):
        return {"requested_mode":"NO_TRADE","strength":strength,"reasons":["no_direction"],"authorizes_execution":False}

    aligned_h4=(side=="BUY" and h4_bias=="UP") or (side=="SELL" and h4_bias=="DOWN")
    adverse_crowding=(
        side=="BUY" and crowding_risk in ("HIGH_LONG_LIQUIDATION","WATCH_LONG_LIQUIDATION","LONG_LIQUIDATION_BIAS")
    ) or (
        side=="SELL" and crowding_risk in ("HIGH_SHORT_SQUEEZE","WATCH_SHORT_SQUEEZE","SHORT_SQUEEZE_BIAS")
    )
    shock=macro_regime in ("SHOCK_0_5M","PRE_EVENT")
    stress=vol_state=="STRESS_EXPANSION"

    # Official MAIN is earned by structure + evidence, not by clock alone.
    main_score=0
    if strength >= 6: main_score+=2; reasons.append("strong_technical_alignment")
    elif strength >= 5: main_score+=1; reasons.append("adequate_technical_alignment")
    if confidence >= 8: main_score+=1; reasons.append("high_confidence")
    if aligned_h4: main_score+=2; reasons.append("h4_direction_aligned")
    if alignment in ("STRONG_SUPPORT","SUPPORT"): main_score+=1; reasons.append("gigi_context_supports")
    if market_regime in ("TREND_UP","TREND_DOWN","BREAKOUT","EXPANSION"): main_score+=1; reasons.append("structural_regime")
    if adverse_crowding: main_score-=2; reasons.append("adverse_crowding_risk")
    if shock: main_score-=3; reasons.append("macro_shock_gate")
    if stress: main_score-=1; reasons.append("volatility_stress")

    if main_score >= 5 and strength >= 5 and aligned_h4 and not shock:
        mode="MAIN"
    elif strength >= 3 and not shock:
        mode="SNIPER"
        reasons.append("tactical_evidence_only")
    else:
        mode="NO_TRADE"
        reasons.append("insufficient_or_event_blocked")

    return {
        "requested_mode":mode,
        "strength":strength,
        "main_score":main_score,
        "aligned_h4":aligned_h4,
        "adverse_crowding":adverse_crowding,
        "session":session,
        "reasons":reasons,
        "authorizes_execution":False,
        "note":"analysis_request_only_not_order_authorization",
    }
