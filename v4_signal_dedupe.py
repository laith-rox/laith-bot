"""Event-driven V4 manual Telegram signal deduplication.

Polling may be periodic; publishing happens only when an actionable setup
changes materially. Caller supplies validated candidate and persistent Store.
No broker orders or network access here.
"""


def signal_identity(candidate):
    if not isinstance(candidate, dict):
        return None
    if candidate.get("state") != "READY":
        return None
    side = candidate.get("side")
    if side not in ("BUY", "SELL"):
        return None
    try:
        entry = round(float(candidate["entry"]), 2)
        stop = round(float(candidate["stop"]), 2)
        target = round(float(candidate["target"]), 2)
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
    import math
    if not all(math.isfinite(x) and x > 0 for x in (entry, stop, target)):
        return None
    if side == "BUY" and not (stop < entry < target):
        return None
    if side == "SELL" and not (target < entry < stop):
        return None
    horizon = candidate.get("horizon") or "SCALP"
    return "%s:%s:%.2f:%.2f:%.2f" % (horizon, side, entry, stop, target)


def should_publish_signal(store, candidate, *, session_id):
    """False for invalid/repeated signals within the same verified session."""
    identity = signal_identity(candidate)
    if not identity or not session_id:
        return False
    return not store.get("v4_signal_published:%s:%s" % (session_id, identity))


def mark_signal_published(store, candidate, *, session_id):
    identity = signal_identity(candidate)
    if not identity or not session_id:
        raise ValueError("valid session and ready candidate required")
    store.set("v4_signal_published:%s:%s" % (session_id, identity), True)
