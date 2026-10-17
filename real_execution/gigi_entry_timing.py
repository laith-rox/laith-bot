"""Entry-timing quality for Gigi shadow analysis.

Detects whether a technically valid setup is being considered after a stretched
move (chase risk), on accepted breakout structure, or after a liquidity sweep.
This is research-only context: it never opens, blocks, sizes or modifies orders.
"""
from __future__ import annotations


def _atr(rows, period=14):
    rows=list(rows or [])
    if len(rows)<2:
        return 0.0
    trs=[]
    start=max(1,len(rows)-period)
    for i in range(start,len(rows)):
        prev=float(rows[i-1]["close"])
        hi=float(rows[i]["high"])
        lo=float(rows[i]["low"])
        trs.append(max(hi-lo,abs(hi-prev),abs(lo-prev)))
    return sum(trs)/len(trs) if trs else 0.0


def assess(signal=None, m5=None, session_profile=None, liquidity=None, volatility=None):
    signal=signal or {}
    rows=list(m5 or [])
    session_profile=session_profile or {}
    liquidity=liquidity or {}
    volatility=volatility or {}

    side=str(signal.get("side") or "WAIT").upper()
    if side not in ("BUY","SELL") or len(rows)<6:
        return {
            "state":"UNKNOWN",
            "posture":"REVIEW_ONLY",
            "directional_impulse_atr":None,
            "last_bar_range_atr":None,
            "vwap_distance_atr":session_profile.get("vwap_distance_atr"),
            "reasons":["insufficient_timing_context"],
            "directional_signal":False,
            "execution_gate":False,
        }

    atr=max(_atr(rows,14),1e-9)
    last=rows[-1]
    close=float(last["close"])
    prior=float(rows[-4]["close"])
    signed=(close-prior)/atr
    directional=signed if side=="BUY" else -signed
    last_range=(float(last["high"])-float(last["low"]))/atr

    try:
        vwap_distance=float(session_profile.get("vwap_distance_atr"))
    except Exception:
        vwap_distance=None
    extension=str(session_profile.get("extension_state") or "UNKNOWN").upper()
    range_event=str(session_profile.get("range_event") or "UNKNOWN").upper()
    liq_event=str(liquidity.get("event") or "UNKNOWN").upper()
    vol_state=str(volatility.get("state") or "UNKNOWN").upper()

    reasons=[]
    matching_breakout=(
        (side=="BUY" and range_event=="ACCEPTED_ABOVE") or
        (side=="SELL" and range_event=="ACCEPTED_BELOW")
    )
    matching_sweep=(
        (side=="BUY" and liq_event=="SELL_SIDE_SWEEP") or
        (side=="SELL" and liq_event=="BUY_SIDE_SWEEP")
    )

    stretched=(
        directional >= 1.50
        or last_range >= 1.60
        or extension=="EXTENDED"
        or (vwap_distance is not None and abs(vwap_distance)>=1.50)
    )
    moderate_impulse=0.25 <= directional < 1.50

    if stretched and not matching_sweep:
        state="CHASE_RISK"
        posture="WAIT_FOR_RETEST_SHADOW"
        reasons.append("entry_after_stretched_directional_move")
    elif matching_sweep:
        state="LIQUIDITY_RETEST"
        posture="REVERSAL_TIMING_CONTEXT"
        reasons.append("liquidity_sweep_matches_entry_side")
    elif matching_breakout and moderate_impulse:
        state="BREAKOUT_ACCEPTANCE"
        posture="ACCEPTANCE_TIMING_CONTEXT"
        reasons.append("accepted_breakout_without_extreme_stretch")
    elif extension=="FAIR_VALUE_ZONE" and abs(directional)<0.90:
        state="BALANCED_ENTRY_ZONE"
        posture="BALANCED_TIMING_CONTEXT"
        reasons.append("near_session_fair_value")
    else:
        state="NEUTRAL"
        posture="REVIEW_ONLY"
        reasons.append("no_strong_timing_edge")

    if vol_state in ("STRESS_EXPANSION","REALIZED_EXPANSION"):
        reasons.append("volatility_expansion_can_increase_slippage_and_retest_depth")
    elif vol_state=="PRICED_MOVE_COMPRESSION":
        reasons.append("options_price_move_before_realized_break")

    return {
        "state":state,
        "posture":posture,
        "directional_impulse_atr":round(float(directional),3),
        "last_bar_range_atr":round(float(last_range),3),
        "vwap_distance_atr":None if vwap_distance is None else round(vwap_distance,3),
        "matching_breakout":bool(matching_breakout),
        "matching_liquidity_sweep":bool(matching_sweep),
        "reasons":reasons,
        "directional_signal":False,
        "execution_gate":False,
        "note":"entry_timing_shadow_context_not_order_rule",
    }
