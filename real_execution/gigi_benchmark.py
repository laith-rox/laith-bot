"""LBMA benchmark-auction timing context for Gigi shadow analysis.

The LBMA Gold Price auctions commence at 10:30 and 15:00 London time. This
module tags proximity to those benchmark windows using a DST-aware London
clock. It is context only: auction proximity is not BUY/SELL.
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:  # pragma: no cover
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

UTC = timezone.utc
try:
    LONDON = ZoneInfo("Europe/London") if ZoneInfo is not None else UTC
    TZ_SOURCE = "IANA_EUROPE_LONDON" if ZoneInfo is not None else "UTC_FALLBACK"
except ZoneInfoNotFoundError:  # pragma: no cover
    LONDON = UTC
    TZ_SOURCE = "UTC_FALLBACK"

AUCTIONS = (
    ("LBMA_AM", 10 * 60 + 30),
    ("LBMA_PM", 15 * 60),
)
PRE_MINUTES = 15
POST_MINUTES = 15


def _parse(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("benchmark_timestamp_missing")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def context(value):
    utc = _parse(value)
    local = utc.astimezone(LONDON)
    minute = local.hour * 60 + local.minute

    nearest = None
    best_abs = None
    for name, auction_minute in AUCTIONS:
        delta = minute - auction_minute
        distance = abs(delta)
        if best_abs is None or distance < best_abs:
            best_abs = distance
            nearest = (name, auction_minute, delta)

    name, auction_minute, delta = nearest
    if -PRE_MINUTES <= delta < 0:
        phase = "PRE_AUCTION"
    elif 0 <= delta <= POST_MINUTES:
        phase = "AUCTION_OR_IMMEDIATE_POST"
    else:
        phase = "OUTSIDE_AUCTION_WINDOW"

    return {
        "phase": phase,
        "nearest_auction": name,
        "minutes_from_auction": int(delta),
        "london_local": local.isoformat(),
        "london_minute": minute,
        "auction_london_minute": auction_minute,
        "timezone_source": TZ_SOURCE,
        "directional_signal": False,
        "note": "lbma_benchmark_timing_context_not_entry_signal",
    }
