"""Broker execution-quality context for Gigi shadow analysis.

Uses the REAL broker bid/ask spread and tick freshness relative to recent M15
range. It never chooses BUY/SELL and never moves or opens an order. Terminal
AutoTrading is treated separately as a hard preflight fact by the REAL bridge.
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


def analyze(health, m15, volatility=None):
    health=health or {}
    volatility=volatility or {}

    spread=health.get("spread_usd")
    tick_age=health.get("tick_age_seconds")
    terminal=health.get("terminal_trade_allowed")
    atr=_atr(m15,14)

    try:
        spread=float(spread)
    except Exception:
        spread=None
    try:
        tick_age=float(tick_age)
    except Exception:
        tick_age=None

    if terminal is False:
        quality="BLOCKED_TERMINAL"
    elif tick_age is not None and tick_age > 10:
        quality="STALE_TICK"
    elif spread is None or spread < 0 or atr <= 0:
        quality="UNKNOWN"
    else:
        ratio=spread/atr
        vol_state=str(volatility.get("state") or "UNKNOWN").upper()
        if ratio >= 0.15:
            quality="EXTREME"
        elif ratio >= 0.08:
            quality="WIDE"
        elif ratio >= 0.05 and vol_state in ("STRESS_EXPANSION","REALIZED_EXPANSION"):
            quality="WIDE"
        else:
            quality="NORMAL"

    ratio=None if spread is None or atr <= 0 else spread/atr
    if ratio is None:
        bucket="UNKNOWN"
    elif ratio < 0.03:
        bucket="LT_3PCT_ATR"
    elif ratio < 0.05:
        bucket="3_TO_5PCT_ATR"
    elif ratio < 0.08:
        bucket="5_TO_8PCT_ATR"
    elif ratio < 0.15:
        bucket="8_TO_15PCT_ATR"
    else:
        bucket="GE_15PCT_ATR"

    return {
        "quality":quality,
        "spread_usd":None if spread is None else round(spread,5),
        "m15_atr":None if atr <= 0 else round(atr,5),
        "spread_atr_ratio":None if ratio is None else round(ratio,4),
        "spread_atr_bucket":bucket,
        "tick_age_seconds":None if tick_age is None else round(tick_age,2),
        "terminal_trade_allowed":terminal,
        "volatility_state":str(volatility.get("state") or "UNKNOWN").upper(),
        "directional_signal":False,
        "note":"execution_quality_context_not_direction",
    }
