"""Scheduled USD high-impact entry blackout; existing signals keep being monitored."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib

import requests

from market import UTC, timestamp

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NY = ZoneInfo("America/New_York")


def week_start(now):
    local = now.astimezone(NY)
    return (local - timedelta(days=(local.weekday() + 1) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)


def parse_calendar(payload, now):
    if not isinstance(payload, list) or not payload:
        raise ValueError("calendar_empty")
    start = week_start(now)
    dates, events = [], []
    for row in payload:
        dt = timestamp(row["date"])
        if datetime.fromisoformat(row["date"]).tzinfo is None:
            raise ValueError("calendar_timezone_missing")
        dates.append(dt)
        if row["country"] == "USD" and row["impact"] == "High":
            title = str(row["title"])[:180]
            key = title + dt.isoformat()
            events.append({"id": hashlib.sha256(key.encode()).hexdigest()[:16],
                           "title": title, "time": dt.timestamp()})
    if min(dates) < start or max(dates) >= start + timedelta(days=7):
        raise ValueError("calendar_wrong_week")
    return sorted(events, key=lambda e: e["time"])


class NewsGuard:
    def __init__(self, store, session=None):
        self.store = store
        self.session = session or requests.Session()

    def check(self, now):
        current = now.timestamp()
        cache = self.store.get("calendar")
        last_attempt = self.store.get("calendar_attempt", 0)
        if (not cache or current - cache["fetched"] >= 3600) and current - last_attempt >= 600:
            self.store.set("calendar_attempt", current)
            try:
                response = self.session.get(FEED, timeout=(5, 15))
                if response.status_code != 200:
                    raise ValueError("calendar_http_error")
                events = parse_calendar(response.json(), now)
                cache = {"fetched": current, "week": week_start(now).isoformat(), "events": events}
                self.store.set("calendar", cache)
            except (requests.RequestException, ValueError, TypeError, KeyError):
                self.store.set("calendar_error", "calendar_unavailable")
        if (not cache or not 0 <= current - cache["fetched"] <= 7200
                or cache["week"] != week_start(now).isoformat()):
            return False, "calendar_unavailable", []
        near = [e for e in cache["events"] if -15*60 <= e["time"] - current <= 30*60]
        return not near, "news_blackout" if near else "calendar_clear", near
