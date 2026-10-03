"""Concurrent-position exposure context for Gigi shadow analysis.

Laith allows MAIN and SNIPER positions to coexist. This module does not block
that. It only makes same-direction stacking visible so multiple valid-looking
entries are not mistaken for independent risk.
"""
from __future__ import annotations


def analyze(health=None, signal=None):
    health=health or {}
    signal=signal or {}
    side=str(signal.get("side") or "WAIT").upper()
    mode="MAIN" if str(signal.get("mode") or "").upper()=="MAIN" else "SNIPER"

    buy_count=int(health.get("owned_buy_count") or 0)
    sell_count=int(health.get("owned_sell_count") or 0)
    main_buy=int(health.get("main_buy_count") or 0)
    main_sell=int(health.get("main_sell_count") or 0)
    sniper_buy=int(health.get("sniper_buy_count") or 0)
    sniper_sell=int(health.get("sniper_sell_count") or 0)

    if side=="BUY":
        same=buy_count
        opposite=sell_count
        same_mode=main_buy if mode=="MAIN" else sniper_buy
        cross_mode=sniper_buy if mode=="MAIN" else main_buy
    elif side=="SELL":
        same=sell_count
        opposite=buy_count
        same_mode=main_sell if mode=="MAIN" else sniper_sell
        cross_mode=sniper_sell if mode=="MAIN" else main_sell
    else:
        same=opposite=same_mode=cross_mode=0

    if same >= 3:
        stacking="HIGH_CONCENTRATION"
    elif same == 2:
        stacking="CONCENTRATED"
    elif same == 1:
        stacking="LAYERED"
    else:
        stacking="CLEAR"

    if same > 0 and opposite > 0:
        book="TWO_SIDED"
    elif same > 0:
        book="SAME_DIRECTION"
    elif opposite > 0:
        book="OPPOSITE_DIRECTION_OPEN"
    else:
        book="FLAT"

    reasons=[]
    if same_mode>0:
        reasons.append("same_mode_same_side_open")
    if cross_mode>0:
        reasons.append("cross_mode_same_side_open")
    if opposite>0:
        reasons.append("opposite_side_open")
    if stacking in ("CONCENTRATED","HIGH_CONCENTRATION"):
        reasons.append("same_direction_risk_concentration")

    return {
        "proposed_side":side,
        "proposed_mode":mode,
        "same_side_open_count":same,
        "opposite_side_open_count":opposite,
        "same_mode_same_side_count":same_mode,
        "cross_mode_same_side_count":cross_mode,
        "stacking_state":stacking,
        "book_state":book,
        "reasons":reasons,
        "directional_signal":False,
        "execution_gate":False,
        "note":"concurrent_exposure_context_not_entry_block",
    }
