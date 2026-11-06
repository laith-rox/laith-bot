"""V4 manual Telegram opportunity planning; pure logic, no execution APIs."""
from dataclasses import dataclass
from enum import Enum


class OpportunityState(str, Enum):
    WATCH = "WATCH"
    READY = "READY"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"


class Horizon(str, Enum):
    SCALP = "SCALP"
    INTRADAY = "INTRADAY"
    SWING = "SWING"


@dataclass(frozen=True)
class ManualPlan:
    side: str
    horizon: Horizon
    entry: float
    stop: float
    target: float
    state: OpportunityState
    reason: str
    reward_to_risk: float


def build_manual_plan(side, horizon, entry, stop, target, *, confirmed=False,
                      quote_fresh=False, session_open=False, news_safe=False,
                      minimum_rr=1.5):
    """Reject incoherent or unsafe candidates; never places a trade.

    Prices must be supplied from validated market data by the caller.
    """
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    horizon = Horizon(horizon)
    entry, stop, target = float(entry), float(stop), float(target)
    if not all(map(lambda v: v > 0 and v < float("inf"), (entry, stop, target))):
        raise ValueError("invalid price")
    if side == "BUY" and not (stop < entry < target):
        raise ValueError("BUY stop/target geometry invalid")
    if side == "SELL" and not (target < entry < stop):
        raise ValueError("SELL stop/target geometry invalid")
    rr = abs(target - entry) / abs(entry - stop)
    if not session_open:
        state, reason = OpportunityState.INVALID, "market_closed"
    elif not quote_fresh:
        state, reason = OpportunityState.INVALID, "quote_unverified"
    elif not news_safe:
        state, reason = OpportunityState.WATCH, "news_risk"
    elif rr < minimum_rr:
        state, reason = OpportunityState.INVALID, "insufficient_reward_to_risk"
    elif not confirmed:
        state, reason = OpportunityState.WATCH, "awaiting_price_confirmation"
    else:
        state, reason = OpportunityState.READY, "confirmed_manual_entry"
    return ManualPlan(side, horizon, entry, stop, target, state, reason, round(rr, 2))
