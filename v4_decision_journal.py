"""Bounded, restart-safe V4 decision journal for audit and missed-opportunity review.

Records only information available at decision time. It does not backfill
future prices, fabricate outcomes, or place any trade.
"""
from datetime import datetime, timezone
import math

JOURNAL_KEY = "v4_decision_journal_v1"


def record_candidate(store, *, observed_at, slot, side, state, reason,
                     entry=None, score=None, limit=500):
    """Persist a deduplicated candidate decision; return True if newly stored.

    The event identity includes the decision reason so a WAIT->READY change
    within a slot is retained, while repeated polling is deduplicated.
    """
    if state not in ("READY", "WAIT", "REJECTED", "INVALID"):
        return False
    if side not in ("BUY", "SELL", "WAIT"):
        return False
    if not isinstance(reason, str) or not reason or len(reason) > 160:
        return False
    if not isinstance(slot, (str, int)) or not str(slot) or len(str(slot)) > 80:
        return False
    try:
        ts = float(observed_at)
        if not math.isfinite(ts) or ts <= 0:
            return False
        dt = datetime.fromtimestamp(ts, timezone.utc)
        if entry is not None:
            entry = float(entry)
            if not math.isfinite(entry) or entry <= 0:
                return False
        if score is not None:
            score = int(score)
            if not 0 <= score <= 7:
                return False
    except (TypeError, ValueError, OverflowError, OSError):
        return False
    limit = max(1, min(int(limit), 2000))
    key = f"{slot}|{side}|{state}|{reason}"
    old = store.get(JOURNAL_KEY) or []
    if not isinstance(old, list):
        old = []
    if any(isinstance(event, dict) and event.get("key") == key for event in old):
        return False
    event = {"key": key, "observed_at": dt.isoformat(), "slot": str(slot),
             "side": side, "state": state, "reason": reason,
             "entry": entry, "score": score, "manual_only": True}
    store.set(JOURNAL_KEY, (old + [event])[-limit:])
    return True


def journal_summary(events):
    """Summarize logged decisions without pretending these are trade results."""
    events = events if isinstance(events, list) else []
    states = {name: 0 for name in ("READY", "WAIT", "REJECTED", "INVALID")}
    reasons = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        state = event.get("state")
        if state not in states:
            continue
        states[state] += 1
        if state != "READY":
            reason = event.get("reason")
            if isinstance(reason, str):
                reasons[reason] = reasons.get(reason, 0) + 1
    return {"decision_count": sum(states.values()), "states": states,
            "block_reasons": dict(sorted(reasons.items(), key=lambda p: (-p[1], p[0]))),
            "win_rate": None, "note": "decision counts only; no measured trade outcomes"}
