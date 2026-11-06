"""Broker-calendar-driven market guard, isolated from production runtime.

Intervals are authoritative UTC open/close timestamps supplied by a validated
broker calendar. This module intentionally does not guess XAUUSD market hours.
"""
from datetime import datetime, timedelta, timezone


def market_guard(now, intervals, *, warning_minutes=30, last_quote_at=None,
                 max_quote_age_seconds=90):
    """Return (state, next_close, reason) for a timezone-aware UTC instant.

    intervals: iterable of (open_utc, close_utc) pairs. Missing calendar fails closed.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)
    windows = sorted((a.astimezone(timezone.utc), b.astimezone(timezone.utc))
                     for a, b in intervals if a.tzinfo and b.tzinfo and a < b)
    if not windows:
        return "CLOSED", None, "missing_verified_broker_calendar"
    for opened, closes in windows:
        if opened <= now < closes:
            if last_quote_at is None or last_quote_at.tzinfo is None:
                return "WAIT", closes, "fresh_quote_unverified"
            age = (now - last_quote_at.astimezone(timezone.utc)).total_seconds()
            if age < 0 or age > max_quote_age_seconds:
                return "WAIT", closes, "stale_or_future_quote"
            if closes - now <= timedelta(minutes=warning_minutes):
                return "PRE_CLOSE", closes, "last_30_minutes"
            return "OPEN", closes, "verified_session"
    return "CLOSED", None, "outside_broker_session"


def close_alert_key(close_at, *, weekly=False):
    """Stable key for exactly-once Telegram warning persisted by caller."""
    if close_at is None or close_at.tzinfo is None:
        raise ValueError("close timestamp required")
    return "v4_close_warning:%s:%s" % (
        close_at.astimezone(timezone.utc).isoformat(), "weekly" if weekly else "daily")


def valid_post_open_quote(quote_at, opened_at, now, *, max_age_seconds=90):
    """Prevent replaying a pre-close quote after session reopening."""
    if any(t is None or t.tzinfo is None for t in (quote_at, opened_at, now)):
        return False
    return (opened_at <= quote_at <= now and
            (now - quote_at).total_seconds() <= max_age_seconds)
