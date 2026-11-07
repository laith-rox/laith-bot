"""Strict adapter for externally verified V4 broker sessions and news events.

No inferred broker hours or economic release times. An operator must explicitly
provide an ISO-8601 UTC schedule and mark it verified; malformed input fails closed.
"""
import json
from datetime import datetime, timezone, timedelta


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
        if (not isinstance(payload, dict) or payload.get("verified") is not True
                or not isinstance(payload.get("sessions"), list)):
            return ()
        intervals = []
        for entry in payload["sessions"]:
            opened, closed = _utc(entry["open"]), _utc(entry["close"])
            # One broker session cannot span multiple days. A typo or a
            # week-long interval must never authorize weekend entries.
            if opened >= closed or closed - opened > timedelta(hours=24):
                return ()
            # A purported broker window must never authorize Saturday trading.\n            # Check every UTC date touched, not only the opening date.\n            cursor = opened.date()\n            last_date = (closed - timedelta(microseconds=1)).date()\n            while cursor <= last_date:\n                if cursor.weekday() == 5:\n                    return ()\n                cursor += timedelta(days=1)\n            intervals.append((opened, closed))
        intervals.sort()
        # Conflicting broker windows are ambiguous: never authorize an entry.
        if any(previous[1] > current[0] for previous, current in zip(intervals, intervals[1:])):
            return ()
        return tuple(intervals)
    except (ValueError, TypeError, KeyError, AttributeError):
        return ()


def verified_news(raw):
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
        if (not isinstance(payload, dict) or payload.get("verified") is not True
                or not isinstance(payload.get("events"), list)):
            return ()
        events = []
        seen_ids = set()
        seen_releases = set()
        for event in payload["events"]:
            if (not isinstance(event, dict) or not isinstance(event.get("title"), str)
                    or not event["title"].strip()):
                return ()
            # Duplicate IDs can carry conflicting times and bypass news blackout logic.
            event_id = event.get("id")
            if event_id is not None:
                if not isinstance(event_id, str) or not event_id.strip():
                    return ()
                normalized_id = event_id.strip().casefold()
                if normalized_id in seen_ids:
                    return ()
                seen_ids.add(normalized_id)
            e = dict(event)
            e["release_at"] = _utc(e["release_at"])
            if e.get("actual_published_at") is not None:
                e["actual_published_at"] = _utc(e["actual_published_at"])
            # An event without an ID can otherwise be duplicated under the same
            # release and title, generating repeated alerts from one calendar.
            release_key = (e["title"].strip().casefold(), e["release_at"])
            if release_key in seen_releases:
                return ()
            seen_releases.add(release_key)
            e["calendar_verified"] = True
            events.append(e)
        return tuple(events)
    except (ValueError, TypeError, KeyError, AttributeError):
        return ()


def verified_entry_calendar_available(raw):
    """No new or retried manual-entry alert without an explicit verified session."""
    return bool(verified_sessions(raw))
