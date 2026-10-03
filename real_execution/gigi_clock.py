"""Palestine-local clock helpers for Gigi.

Uses IANA Asia/Hebron so session windows follow daylight-saving changes rather
than assuming UTC+3 all year. Falls back to +03 only if timezone data is
unavailable, and exposes the fallback so it is visible in diagnostics.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:  # pragma: no cover
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

ZONE_NAME = "Asia/Hebron"
FALLBACK = timezone(timedelta(hours=3))

try:
    PALESTINE_TZ = ZoneInfo(ZONE_NAME) if ZoneInfo is not None else FALLBACK
    TIMEZONE_SOURCE = "IANA_ASIA_HEBRON" if ZoneInfo is not None else "FALLBACK_UTC_PLUS_3"
except ZoneInfoNotFoundError:
    PALESTINE_TZ = FALLBACK
    TIMEZONE_SOURCE = "FALLBACK_UTC_PLUS_3"


def parse_utc(value):
    raw=str(value or "").strip()
    if not raw:
        raise ValueError("timestamp_missing")
    dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def local_datetime(value):
    return parse_utc(value).astimezone(PALESTINE_TZ)


def local_minute(value):
    dt=local_datetime(value)
    return dt.hour*60+dt.minute


def context(value):
    dt=local_datetime(value)
    offset=dt.utcoffset()
    return {
        "timezone":ZONE_NAME,
        "timezone_source":TIMEZONE_SOURCE,
        "local_iso":dt.isoformat(),
        "utc_offset_hours":None if offset is None else round(offset.total_seconds()/3600.0,2),
        "local_minute":dt.hour*60+dt.minute,
    }
