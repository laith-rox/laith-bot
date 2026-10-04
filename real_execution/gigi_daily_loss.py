"""Daily account loss circuit breaker for Gigi candidate execution.

Pure policy: it never places or closes orders. The executor supplies today's
realized P/L for Gigi-owned trades. Limits scale from start-of-day equity so a
configured dollar amount can never silently exceed the account's capacity.
"""
from __future__ import annotations

DAILY_LOSS_PCT = 0.10
MAX_CONSECUTIVE_LOSSES = 3


def limits(start_equity):
    eq=max(0.0,float(start_equity or 0.0))
    return {
        "daily_loss_cap_usd": round(eq*DAILY_LOSS_PCT,4),
        "daily_loss_pct": DAILY_LOSS_PCT,
        "max_consecutive_losses": MAX_CONSECUTIVE_LOSSES,
    }


def validate(realized_pnl, consecutive_losses, start_equity):
    try:
        pnl=float(realized_pnl)
        losses=int(consecutive_losses)
        eq=float(start_equity)
    except Exception:
        return {"ok":False,"reason":"daily_loss_inputs_invalid"}
    if eq <= 0 or losses < 0:
        return {"ok":False,"reason":"daily_loss_inputs_invalid"}

    lim=limits(eq)
    loss=max(0.0,-pnl)
    if loss >= float(lim["daily_loss_cap_usd"]) - 0.001:
        return {**lim,"ok":False,"reason":"daily_loss_cap_reached","realized_pnl":round(pnl,4)}
    if losses >= int(lim["max_consecutive_losses"]):
        return {**lim,"ok":False,"reason":"consecutive_loss_circuit_breaker","realized_pnl":round(pnl,4)}
    return {**lim,"ok":True,"reason":"approved","realized_pnl":round(pnl,4)}
