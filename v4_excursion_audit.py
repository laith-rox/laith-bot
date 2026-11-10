"""Hindsight-safe V4 advisory candidate outcome audit.

Only bars fully closed by as_of may contribute to MFE/MAE. Does not place
orders or assert simulated profits. Intrabar path and fills remain unknown.
"""
from datetime import datetime, timezone
import math


def audit_excursion(*, side, entry_price, entry_at, as_of, closed_bars):
    """Return price excursions since an observed manual signal.

    All timestamps must be aware UTC-compatible datetimes. Bars with end after
    as_of, or beginning before entry_at, are excluded; this avoids lookahead
    and partial-entry-candle assumptions. Return insufficient_data when empty.
    """
    if side not in ("BUY", "SELL"):
        return {"status": "invalid_side"}
    try:
        entry_price = float(entry_price)
        if not math.isfinite(entry_price) or entry_price <= 0:
            raise ValueError("invalid entry")
        if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None
               for t in (entry_at, as_of)) or as_of < entry_at:
            raise ValueError("invalid timestamp")
        extrema = []
        for bar in closed_bars:
            def field(k):
                return bar[k] if isinstance(bar, dict) else getattr(bar, k)
            start, end = field("start"), field("end")
            if (not isinstance(start, datetime) or not isinstance(end, datetime)
                    or start.tzinfo is None or end.tzinfo is None
                    or start.utcoffset() is None or end.utcoffset() is None
                    or end <= start):
                raise ValueError("invalid bar timestamps")
            if start < entry_at or end > as_of:
                continue
            high, low = float(field("high")), float(field("low"))
            if not all(math.isfinite(x) and x > 0 for x in (high, low)) or high < low:
                raise ValueError("invalid bar prices")
            extrema.append((high, low))
        if not extrema:
            return {"status": "insufficient_data", "bars_used": 0}
        best_high = max(h for h, _ in extrema)
        worst_low = min(l for _, l in extrema)
        favorable = best_high - entry_price if side == "BUY" else entry_price - worst_low
        adverse = entry_price - worst_low if side == "BUY" else best_high - entry_price
        return {"status": "observed", "bars_used": len(extrema),
                "mfe_price": round(max(0.0, favorable), 6),
                "mae_price": round(max(0.0, adverse), 6),
                "as_of": as_of.astimezone(timezone.utc).isoformat(),
                "manual_only": True, "fill_assumed": False}
    except (ValueError, TypeError, AttributeError, KeyError, OverflowError):
        return {"status": "invalid_data"}
