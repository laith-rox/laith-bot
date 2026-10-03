"""Target-geometry context for Gigi shadow learning.

Compares the proposed target distance with recent M15 ATR and, when available,
the GLD-options 1-day implied-move proxy. Descriptive only: it does not change
TPs, approve trades, or convert an options proxy into a price target.
"""
from __future__ import annotations


def _atr(rows, period=14):
    rows=list(rows or [])
    if len(rows) < period + 1:
        return 0.0
    trs=[]
    for i in range(max(1,len(rows)-period),len(rows)):
        prev=float(rows[i-1]["close"])
        high=float(rows[i]["high"])
        low=float(rows[i]["low"])
        trs.append(max(high-low,abs(high-prev),abs(low-prev)))
    return sum(trs)/len(trs) if trs else 0.0


def analyze(signal, m15, options=None):
    signal=signal or {}
    options=options or {}

    entry=float(signal.get("reference_close") or 0.0)
    risk=float(signal.get("risk_distance") or 0.0)
    target_r=float(signal.get("target_r") or 0.0)
    atr=_atr(m15,14)

    if entry <= 0 or risk <= 0 or target_r <= 0 or atr <= 0:
        return {
            "state":"UNKNOWN",
            "target_atr_bucket":"UNKNOWN",
            "implied_move_relation":"UNKNOWN",
            "directional_signal":False,
            "execution_gate":False,
            "note":"shadow_target_geometry_not_tp_instruction",
        }

    target_distance=risk*target_r
    target_atr=target_distance/atr

    if target_atr < 0.75:
        atr_bucket="SUB_0_75_ATR"
    elif target_atr < 1.50:
        atr_bucket="0_75_TO_1_5_ATR"
    elif target_atr < 3.0:
        atr_bucket="1_5_TO_3_ATR"
    else:
        atr_bucket="GT_3_ATR"

    implied_pct=options.get("expected_move_1d_pct")
    implied_distance=None
    implied_ratio=None
    implied_relation="UNKNOWN"
    try:
        implied_pct=float(implied_pct)
        if implied_pct > 0:
            implied_distance=entry*(implied_pct/100.0)
            implied_ratio=target_distance/implied_distance
            if implied_ratio <= 0.75:
                implied_relation="WELL_WITHIN_1D_PROXY"
            elif implied_ratio <= 1.25:
                implied_relation="AROUND_1D_PROXY"
            elif implied_ratio <= 1.75:
                implied_relation="STRETCHED_1D_PROXY"
            else:
                implied_relation="FAR_BEYOND_1D_PROXY"
    except Exception:
        pass

    if implied_relation=="FAR_BEYOND_1D_PROXY" and target_atr>=3.0:
        state="AMBITION_HIGH"
    elif implied_relation in ("FAR_BEYOND_1D_PROXY","STRETCHED_1D_PROXY"):
        state="AMBITION_ELEVATED"
    elif target_atr < 0.75:
        state="SHORT_HORIZON"
    else:
        state="BALANCED_CONTEXT"

    return {
        "state":state,
        "target_distance":round(target_distance,5),
        "target_r":round(target_r,3),
        "m15_atr":round(atr,5),
        "target_atr_ratio":round(target_atr,3),
        "target_atr_bucket":atr_bucket,
        "implied_move_1d_pct_proxy":None if implied_pct is None else round(float(implied_pct),3),
        "implied_move_distance_proxy":None if implied_distance is None else round(implied_distance,5),
        "target_to_implied_move_ratio":None if implied_ratio is None else round(implied_ratio,3),
        "implied_move_relation":implied_relation,
        "proxy_note":"GLD_options_expected_move_proxy_not_COMEX_XAU_target",
        "directional_signal":False,
        "execution_gate":False,
        "note":"shadow_target_geometry_not_tp_instruction",
    }
