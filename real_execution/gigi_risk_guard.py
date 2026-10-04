"""Pure fail-closed account risk guard for REAL candidate execution.

No broker calls and no order placement. The hard account cap is mandatory and
is always applied on top of any strategy/mode ceiling.
"""
from __future__ import annotations


def validate(planned_loss, existing_total, existing_mode, hard_cap, equity, mode_budget=None):
    try:
        planned=float(planned_loss)
        total=float(existing_total)
        mode=float(existing_mode)
        eq=float(equity)
    except Exception:
        return {"ok":False,"reason":"risk_inputs_invalid"}

    if hard_cap is None:
        return {"ok":False,"reason":"account_hard_risk_cap_unset"}
    try:
        cap=float(hard_cap)
    except Exception:
        return {"ok":False,"reason":"account_hard_risk_cap_invalid"}

    if min(planned,total,mode) < 0 or cap <= 0 or eq <= 0:
        return {"ok":False,"reason":"risk_inputs_invalid"}
    if planned <= 0:
        return {"ok":False,"reason":"planned_loss_invalid"}

    mode_after=mode+planned
    total_after=total+planned
    if mode_budget is not None:
        try:
            budget=float(mode_budget)
        except Exception:
            return {"ok":False,"reason":"mode_budget_invalid"}
        if budget <= 0:
            return {"ok":False,"reason":"mode_budget_invalid"}
        if mode_after > budget + 0.01:
            return {"ok":False,"reason":"mode_risk_reject","mode_after":round(mode_after,4),"mode_budget":round(budget,4)}

    if total_after > cap + 0.01:
        return {"ok":False,"reason":"account_hard_cap_reject","total_after":round(total_after,4),"hard_cap":round(cap,4)}
    if total_after >= eq:
        return {"ok":False,"reason":"total_risk_exceeds_equity","total_after":round(total_after,4),"equity":round(eq,4)}

    return {
        "ok":True,
        "reason":"approved",
        "planned_loss":round(planned,4),
        "mode_after":round(mode_after,4),
        "total_after":round(total_after,4),
        "hard_cap":round(cap,4),
        "equity":round(eq,4),
    }
