"""Equity-aware risk policy for Gigi candidate execution.

Stop LOCATION remains structural. This module only decides whether the money at
risk is acceptable for the account. It never moves a structural stop closer to
force a trade through.
"""
from __future__ import annotations


def limits(mode, strength, equity):
    eq=max(0.0,float(equity or 0.0))
    mode=str(mode or "").upper()
    s=max(0,min(7,int(strength or 0)))

    if mode=="SNIPER":
        # Medium setup: 2% of equity. Strong: up to 5%.
        pct=0.02 if s <= 5 else 0.05
    elif mode=="MAIN":
        # MAIN may place its stop at structural invalidation, but one idea may
        # not expose more than 5% of current equity.
        pct=0.05
    else:
        pct=0.0

    return {
        "per_trade_cap_usd": round(eq*pct,4),
        "global_open_risk_cap_usd": round(eq*0.10,4),
        "per_trade_pct": pct,
        "global_pct": 0.10,
    }


def validate(planned_loss, existing_total, mode, strength, equity):
    try:
        planned=float(planned_loss)
        existing=float(existing_total)
        eq=float(equity)
    except Exception:
        return {"ok":False,"reason":"equity_risk_inputs_invalid"}
    if planned <= 0 or existing < 0 or eq <= 0:
        return {"ok":False,"reason":"equity_risk_inputs_invalid"}

    lim=limits(mode,strength,eq)
    per_trade=float(lim["per_trade_cap_usd"])
    global_cap=float(lim["global_open_risk_cap_usd"])
    if per_trade <= 0:
        return {"ok":False,"reason":"unknown_trade_mode"}
    if planned > per_trade + 0.001:
        return {**lim,"ok":False,"reason":"per_trade_equity_cap_reject"}
    if existing + planned > global_cap + 0.001:
        return {**lim,"ok":False,"reason":"global_equity_risk_cap_reject"}
    return {**lim,"ok":True,"reason":"approved"}
