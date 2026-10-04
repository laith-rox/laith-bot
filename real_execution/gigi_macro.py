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

try:
    import requests
except Exception:
    requests = None

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


def event_class(title):
    text=str(title or "").strip().lower()
    if not text:
        return "UNKNOWN"
    if "consumer price" in text or text.startswith("cpi") or " cpi" in text:
        return "CPI"
    if "core pce" in text or "pce price" in text or "personal consumption expenditures" in text:
        return "PCE"
    if "producer price" in text or text.startswith("ppi") or " ppi" in text:
        return "PPI"
    if (
        "non-farm" in text or "nonfarm" in text or "payroll" in text
        or "unemployment rate" in text or "average hourly earnings" in text
    ):
        return "LABOR_NFP"
    if "fomc" in text or "federal funds rate" in text or "fed chair" in text or "powell" in text:
        return "FOMC_FED"
    if "jolts" in text or "job openings" in text or "adp" in text or "unemployment claims" in text:
        return "LABOR_OTHER"
    if "ism" in text:
        return "ISM"
    if "retail sales" in text:
        return "RETAIL_SALES"
    if "gross domestic product" in text or text.startswith("gdp") or " gdp" in text:
        return "GDP"
    if "pmi" in text or "purchasing managers" in text:
        return "PMI"
    if "consumer sentiment" in text or "consumer confidence" in text:
        return "SENTIMENT"
    return "OTHER"


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
            title=str(row.get("title") or "")[:180]
            out.append({
                "title": title,
                "event_class": event_class(title),
                "impact": impact.upper(),
                "time": _parse_timestamp(row.get("date")),
                "actual": str(row.get("actual") or "").strip(),
                "forecast": str(row.get("forecast") or "").strip(),
                "previous": str(row.get("previous") or "").strip(),
            })
        except (ValueError, TypeError):
            continue
    out.sort(key=lambda x: x["time"])
    return out


def fetch_events(now=None, opener=None):
    now = time.time() if now is None else float(now)
    if _cache["events"] and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return list(_cache["events"]), _cache["error"]

    try:
        headers={"User-Agent": "Laith-Gigi-Macro/1.0", "Accept": "application/json"}
        if opener is not None:
            req = urllib.request.Request(FEED, headers=headers)
            with opener(req, timeout=8) as res:
                raw = res.read().decode("utf-8")
        elif requests is not None:
            res = requests.get(FEED, timeout=8, headers=headers)
            res.raise_for_status()
            raw = res.text
        else:
            req = urllib.request.Request(FEED, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
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

    last_event_time=max((float(event["time"]) for event in (events or [])), default=None)
    if last_event_time is not None and not future and now > last_event_time:
        calendar_horizon="EXHAUSTED"
    elif events:
        calendar_horizon="ACTIVE"
    elif error:
        calendar_horizon="UNAVAILABLE"
    else:
        calendar_horizon="EMPTY"

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
    elif calendar_horizon=="EXHAUSTED":
        regime = "HORIZON_EXHAUSTED"
        phase = "OUT_OF_HORIZON"
    else:
        regime = "CLEAR"

    active = near_high[0] if near_high else (near_medium[0] if near_medium else None)
    next_event = future[0] if future else None

    # Gold often receives several USD releases at the same timestamp (for
    # example payrolls, unemployment and earnings). Treat that as one event
    # bundle rather than three independent confirmations. FOMC statement /
    # press-conference sequences can also keep price discovery unstable.
    event_bundle=[]
    if active is not None:
        active_time=float(active["time"])
        event_bundle=[
            dict(event)
            for event in (events or [])
            if abs(float(event["time"])-active_time) <= 2*60
            and str(event.get("impact") or "").upper() in ("HIGH","MEDIUM")
        ]
    high_bundle=sum(str(e.get("impact") or "").upper()=="HIGH" for e in event_bundle)
    bundle_classes=sorted({str(e.get("event_class") or "UNKNOWN") for e in event_bundle})
    if len(event_bundle)>=2 and high_bundle>=2:
        bundle_state="MULTI_HIGH_RELEASE"
    elif len(event_bundle)>=2:
        bundle_state="MULTI_RELEASE"
    elif len(event_bundle)==1:
        bundle_state="SINGLE_RELEASE"
    else:
        bundle_state="NONE"

    return {
        "regime": regime,
        "phase": phase,
        "active_event_class": (active or {}).get("event_class", "NONE"),
        "active_event_title": (active or {}).get("title"),
        "active_event_impact": (active or {}).get("impact"),
        "next_event_class": (next_event or {}).get("event_class", "NONE"),
        "next_event_title": (next_event or {}).get("title"),
        "near_high": near_high[:5],
        "near_medium": near_medium[:5],
        "next_events": future[:5],
        "event_bundle_state": bundle_state,
        "event_bundle_size": len(event_bundle),
        "event_bundle_high_count": int(high_bundle),
        "event_bundle_classes": bundle_classes,
        "event_bundle": event_bundle[:6],
        "calendar_horizon": calendar_horizon,
        "calendar_last_event_time": last_event_time,
        "calendar_error": error,
        "method": "weekly_usd_event_calendar",
    }
