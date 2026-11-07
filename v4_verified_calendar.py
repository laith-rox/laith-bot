"""Strict adapter for externally verified V4 broker sessions and news events.

No inferred broker hours or economic release times. An operator must explicitly
provide an ISO-8601 UTC schedule and mark it verified; malformed input fails closed.
"""
import json
from datetime import datetime, timezone


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(timezone.utc)


def verified_sessions(raw):
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
        if payload.get("verified") is not True or not isinstance(payload.get("sessions"), list):
            return ()
        intervals = []
        for entry in payload["sessions"]:
            opened, closed = _utc(entry["open"]), _utc(entry["close"])
            if opened >= closed:
                return ()
            intervals.append((opened, closed))
        return tuple(sorted(intervals))
    except (ValueError, TypeError, KeyError, AttributeError):
        return ()


def verified_news(raw):
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
        if payload.get("verified") is not True or not isinstance(payload.get("events"), list):
            return ()
        events = []
        for event in payload["events"]:
            if not isinstance(event, dict) or not event.get("title"):
                return ()
            e = dict(event)
            e["release_at"] = _utc(e["release_at"])
            if e.get("actual_published_at") is not None:
                e["actual_published_at"] = _utc(e["actual_published_at"])
            e["calendar_verified"] = True
            events.append(e)
        return tuple(events)
    except (ValueError, TypeError, KeyError, AttributeError):
        return ()
