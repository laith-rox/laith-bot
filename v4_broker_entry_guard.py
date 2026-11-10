"""Fail-closed V4 broker-session entry eligibility, including post-reopen freshness.

A verified schedule must be supplied by an independently trusted source.
No guessed broker hours, no execution, no Telegram side effects.
"""
from datetime import datetime, timezone
from v4_market_guard import market_guard, valid_post_open_quote


def broker_entry_eligibility(now, intervals, quote_at, *, bar_end_at=None):
    """Return (allowed, reason) for an entry or a pending-signal retry.

    The live quote and last completed indicator candle must both belong to
    the currently open broker session. Old-session bars cannot trigger entries.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        return False, "invalid_now"
    try:
        state, _, reason = market_guard(now, intervals, last_quote_at=quote_at)
        if state != "OPEN":
            return False, reason
        opened = max((start for start, end in intervals if start <= now < end), default=None)
        if opened is None or not valid_post_open_quote(quote_at, opened, now):
            return False, "quote_before_session_open"
        if bar_end_at is not None:
            if not isinstance(bar_end_at, datetime) or bar_end_at.tzinfo is None:
                return False, "invalid_indicator_bar_time"
            # Last completed bar must not extend beyond the observation time.
            if not (opened <= bar_end_at <= now):
                return False, "indicator_bar_from_previous_session"
            if bar_end_at > quote_at:
                return False, "indicator_bar_newer_than_quote"
        return True, "verified_open_and_fresh"
    except (TypeError, ValueError, AttributeError, OverflowError):
        return False, "invalid_broker_session_data"
