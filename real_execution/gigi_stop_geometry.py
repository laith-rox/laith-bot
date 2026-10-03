"""Stop-geometry context for Gigi shadow learning.

Compares the proposed price-risk distance with recent M15 ATR. This module does
not move stops and does not approve/reject a trade. It only records whether a
stop sits inside or outside recent market noise so the learning layer can later
calibrate which geometry works in each regime.
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


def analyze(signal, m15, volatility=None):
    signal=signal or {}
    volatility=volatility or {}
    risk=float(signal.get("risk_distance") or 0.0)
    atr=_atr(m15,14)
    if risk <= 0 or atr <= 0:
        return {
            "state":"UNKNOWN",
            "risk_atr_ratio":None,
            "noise_exposure":"UNKNOWN",
            "directional_signal":False,
            "note":"shadow_geometry_not_stop_instruction",
        }

    ratio=risk/atr
    if ratio < 0.35:
        bucket="SUB_0_35_ATR"
    elif ratio < 0.75:
        bucket="0_35_TO_0_75_ATR"
    elif ratio < 1.25:
        bucket="0_75_TO_1_25_ATR"
    elif ratio < 2.0:
        bucket="1_25_TO_2_ATR"
    else:
        bucket="GT_2_ATR"

    vol_state=str(volatility.get("state") or "UNKNOWN").upper()
    if ratio < 0.35:
        noise="HIGH"
    elif ratio < 0.75 and vol_state in ("STRESS_EXPANSION","REALIZED_EXPANSION"):
        noise="HIGH"
    elif ratio < 0.75:
        noise="MODERATE"
    else:
        noise="LOW"

    return {
        "state":bucket,
        "risk_atr_ratio":round(ratio,3),
        "m15_atr":round(atr,5),
        "risk_distance":round(risk,5),
        "noise_exposure":noise,
        "mode":str(signal.get("mode") or "UNKNOWN").upper(),
        "volatility_state":vol_state,
        "directional_signal":False,
        "note":"shadow_geometry_not_stop_instruction",
    }
