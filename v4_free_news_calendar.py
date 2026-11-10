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
    clock = payload.get("server_time")
    if not isinstance(clock, (int, float)) or abs(clock - now.timestamp()) > 300:
        raise ValueError("stale_calendar_clock")
    generated = payload.get("generated_at")
    if not isinstance(generated, str):
        raise ValueError("missing_calendar_generation")
    generated_at = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    if generated_at.tzinfo is None or not (now - timedelta(minutes=30) <= generated_at <= now + timedelta(minutes=2)):
        raise ValueError("stale_calendar_snapshot")
    events = []
    for event in payload["events"]:
        if not isinstance(event, dict) or event.get("currency") != "USD" or event.get("impact") not in ("high", "medium"):
            raise ValueError("unexpected_calendar_event")
        if event.get("status") == "tentative" or event.get("confidence") not in ("official", "sources_agree"):
            raise ValueError("uncertain_calendar_event")
        if not event.get("id") or not event.get("title") or not event.get("time"):
            raise ValueError("missing_event_fields")
        # Results are not used to generate an entry; schedule only.
        events.append({"id": event["id"], "title": event["title"], "release_at": event["time"],
                       "impact": event["impact"], "currency": "USD"})
    result = {"verified": True, "verified_at": now.isoformat(), "expires_at": (now + timedelta(minutes=20)).isoformat(), "events": events}
    return json.dumps(result)
