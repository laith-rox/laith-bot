"""Validate a live quote observation timestamp before manual V4 entry."""
import math


def valid_quote_observation(observed_at, now_timestamp, *, max_age=90, future_tolerance=10):
    try:
        observed = float(observed_at)
        current = float(now_timestamp)
    except (TypeError, ValueError, OverflowError):
        return False
    return (math.isfinite(observed) and math.isfinite(current)
            and observed > 0 and current - observed <= max_age
            and observed - current <= future_tolerance)
