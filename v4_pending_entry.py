"""Single decision point for retrying an undelivered manual V4 entry."""
from datetime import datetime
from zoneinfo import ZoneInfo
from v4_quote_observation import valid_quote_observation

NY = ZoneInfo("America/New_York")


def pending_entry_retry_allowed(pending, now, *, market_closed, news_allowed):
    if not isinstance(pending, dict) or not isinstance(now, datetime):
        return False
    if market_closed or not news_allowed:
        return False
    if not all(isinstance(pending.get(key), str) and pending[key] for key in ("session_id", "message")):
        return False
    if not isinstance(pending.get("candidate"), dict):
        return False
    if pending["session_id"] != now.astimezone(NY).date().isoformat():
        return False
    return valid_quote_observation(pending.get("observed_at"), now.timestamp())
