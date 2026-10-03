"""Macro-event context for Gigi REAL shadow analysis.

Uses a weekly USD calendar feed with timezone-aware event timestamps. This
module never places orders and never turns a signal on by itself. It only
classifies event risk so Gigi can distinguish normal market structure from
event-driven conditions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import time
import urllib.request

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE_SECONDS = 1800
PRE_EVENT_SECONDS = 30 * 60
POST_EVENT_SECONDS = 15 * 60

_cache = {"fetched_at": 0.0, "events": [], "error": None}


def _parse_timestamp(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("event_time_missing")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("event_timezone_missing")
    return dt.astimezone(timezone.utc).timestamp()


def parse_events(payload):
    if not isinstance(payload, list):
        raise ValueError("calendar_payload_invalid")
    out = []
    for row in payload:
        try:
            if str(row.get("country") or "").upper() != "USD":
                continue
            impact = str(row.get("impact") or "").strip().lower()
            if impact not in ("high", "medium"):
                continue
            out.append({
                "title": str(row.get("title") or "")[:180],
                "impact": impact.upper(),
                "time": _parse_timestamp(row.get("date")),
            })
        except (ValueError, TypeError):
            continue
    out.sort(key=lambda x: x["time"])
    return out


def fetch_events(now=None, opener=None):
    now = time.time() if now is None else float(now)
    if _cache["events"] and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return list(_cache["events"]), _cache["error"]

    opener = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(
            FEED,
            headers={"User-Agent": "Laith-Gigi-Macro/1.0", "Accept": "application/json"},
        )
        with opener(req, timeout=8) as res:
            raw = res.read().decode("utf-8")
        events = parse_events(json.loads(raw))
        _cache.update({"fetched_at": now, "events": events, "error": None})
        return list(events), None
    except Exception as exc:
        # Keep a still-recent cache if one exists; otherwise report UNKNOWN.
        if _cache["events"] and now - float(_cache["fetched_at"] or 0) <= 7200:
            return list(_cache["events"]), "calendar_refresh_failed"
        _cache.update({"fetched_at": now, "events": [], "error": type(exc).__name__})
        return [], "calendar_unavailable"


def context(at_timestamp=None, events=None, error=None):
    now = time.time() if at_timestamp is None else float(at_timestamp)
    if events is None:
        events, error = fetch_events(now)

    near_high = []
    near_medium = []
    future = []
    for event in events or []:
        delta = float(event["time"]) - now
        if -POST_EVENT_SECONDS <= delta <= PRE_EVENT_SECONDS:
            (near_high if event["impact"] == "HIGH" else near_medium).append(
                dict(event, seconds_to_event=round(delta, 1))
            )
        if delta >= 0:
            future.append(dict(event, seconds_to_event=round(delta, 1)))

    phase = "NORMAL"
    if near_high:
        regime = "HIGH_IMPACT_WINDOW"
        delta = float(near_high[0]["seconds_to_event"])
        if 0 < delta <= PRE_EVENT_SECONDS:
            phase = "PRE_HIGH_EVENT"
        elif -5 * 60 <= delta <= 0:
            phase = "HIGH_EVENT_SHOCK_0_5M"
        else:
            phase = "HIGH_EVENT_DIGESTION_5_15M"
    elif near_medium:
        regime = "MEDIUM_IMPACT_WINDOW"
        delta = float(near_medium[0]["seconds_to_event"])
        if delta > 0:
            phase = "PRE_MEDIUM_EVENT"
        elif delta >= -5 * 60:
            phase = "MEDIUM_EVENT_SHOCK_0_5M"
        else:
            phase = "MEDIUM_EVENT_DIGESTION_5_15M"
    elif error and not events:
        regime = "UNKNOWN"
        phase = "UNKNOWN"
    else:
        regime = "CLEAR"

    return {
        "regime": regime,
        "phase": phase,
        "near_high": near_high[:5],
        "near_medium": near_medium[:5],
        "next_events": future[:5],
        "calendar_error": error,
        "method": "weekly_usd_event_calendar",
    }
