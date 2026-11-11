"""Free economic calendar adapter. Never authorizes an entry on missing/stale data."""
import json
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

URL = "https://showmytrades.com/api/public/calendar/v1?currency=USD&impact=high,medium&days=3"

def fetch_verified_news(now=None, opener=urlopen):
    now = now or datetime.now(timezone.utc)
    req = Request(URL, headers={"User-Agent": "LaithV4-NewsGuard/1.0", "Accept": "application/json"})
    with opener(req, timeout=10) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("invalid_calendar_payload")
    if payload.get("count") is not None and payload["count"] != len(payload["events"]):
        raise ValueError("calendar_count_mismatch")
    clock = payload.get("server_time")
    if type(clock) not in (int, float) or abs(clock - now.timestamp()) > 300:
        raise ValueError("stale_calendar_clock")
    generated = payload.get("generated_at")
    if not isinstance(generated, str):
        raise ValueError("missing_calendar_generation")
    generated_at = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    if generated_at.tzinfo is None or not (now - timedelta(minutes=30) <= generated_at <= now + timedelta(minutes=2)):
        raise ValueError("stale_calendar_snapshot")
    # Cap untrusted payload size before parsing every event; oversized feeds cannot certify safety.
    if len(payload["events"]) > 1000:
        raise ValueError("calendar_too_many_events")
    events = []
    seen_ids = set()
    seen_releases = set()
    for event in payload["events"]:
        if not isinstance(event, dict):
            raise ValueError("invalid_calendar_event")
        if not isinstance(event, dict) or event.get("currency") != "USD" or event.get("impact") not in ("high", "medium"):
            raise ValueError("unexpected_calendar_event")
        if event.get("status") not in ("scheduled", "moved") or event.get("confidence") not in ("official", "sources_agree"):
            raise ValueError("uncertain_calendar_event status=%s confidence=%s" % (str(event.get("status"))[:32], str(event.get("confidence"))[:32]))
        if not event.get("id") or not event.get("title") or not event.get("time"):
            raise ValueError("missing_event_fields")
        if not isinstance(event["time"], str):
            raise ValueError("invalid_release_time")
        try:
            release = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid_release_time") from exc
        if release.tzinfo is None:
            raise ValueError("naive_release_time")
        # A 3-day feed must not certify a calendar full of old/future releases.
        if not (now - timedelta(days=2) <= release.astimezone(timezone.utc) <= now + timedelta(days=5)):
            raise ValueError("release_outside_calendar_window")
        if not isinstance(event["id"], str) or not isinstance(event["title"], str):
            raise ValueError("invalid_event_identity")
        normalized_id = event["id"].strip().casefold()
        release_key = (event["title"].strip().casefold(), release.astimezone(timezone.utc))
        if not normalized_id or not release_key[0] or normalized_id in seen_ids or release_key in seen_releases:
            raise ValueError("duplicate_or_invalid_calendar_event")
        seen_ids.add(normalized_id)
        seen_releases.add(release_key)
        # Results are not used to generate an entry; schedule only.
        events.append({"id": event["id"], "title": event["title"], "release_at": event["time"],
                       "impact": event["impact"], "currency": "USD"})
    result = {"verified": True, "verified_at": now.isoformat(), "expires_at": (now + timedelta(minutes=20)).isoformat(), "events": events}
    return json.dumps(result)
