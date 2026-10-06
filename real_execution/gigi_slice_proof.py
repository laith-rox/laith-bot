"""Granular historical price-only proof for Gigi shadow analysis.

Derived from six non-overlapping 60-day XAUUSD.m broker walk-forward windows
(2025-10-09 through 2026-10-04), with historical spread and conservative
profit-protection replay. External historical macro/options/ETF/CFTC states
were not backfilled, so this is descriptive context only.

It never authorizes execution and never changes size, side, stop or target.
"""
from __future__ import annotations

import gigi_clock

SOURCE = "six_non_overlapping_60d_mt5_price_only_walkforward_20251009_20261004"

SESSION = {
    "MAIN|EARLY_05_10": {"status":"UNSTABLE","n":450,"mean_r":0.1460},
    "MAIN|LONDON_10_13": {"status":"UNSTABLE","n":286,"mean_r":0.1833},
    "MAIN|MIDDAY_13_1520": {"status":"UNSTABLE","n":213,"mean_r":-0.0566},
    "MAIN|US_1520_18": {"status":"UNSTABLE","n":220,"mean_r":-0.1101},
    "MAIN|LATE_18_20": {"status":"INSUFFICIENT_PER_WINDOW","n":225,"mean_r":0.0042},
    "SNIPER|EARLY_05_10": {"status":"STABLE_NEGATIVE","n":4754,"mean_r":-0.0970},
    "SNIPER|LONDON_10_13": {"status":"STABLE_NEGATIVE","n":2753,"mean_r":-0.1016},
    "SNIPER|MIDDAY_13_1520": {"status":"STABLE_NEGATIVE","n":2206,"mean_r":-0.1492},
    "SNIPER|US_1520_18": {"status":"STABLE_NEGATIVE","n":2520,"mean_r":-0.1445},
    "SNIPER|LATE_18_20": {"status":"STABLE_NEGATIVE","n":1587,"mean_r":-0.1493},
}

STRENGTH = {
    "MAIN|5": {"status":"INSUFFICIENT_PER_WINDOW","n":40,"mean_r":0.1752},
    "MAIN|6": {"status":"UNSTABLE","n":779,"mean_r":-0.0059},
    "MAIN|7": {"status":"UNSTABLE","n":572,"mean_r":0.1432},
    "SNIPER|2": {"status":"STABLE_NEGATIVE","n":250,"mean_r":-0.1750},
    "SNIPER|3": {"status":"STABLE_NEGATIVE","n":1316,"mean_r":-0.1058},
    "SNIPER|4": {"status":"UNSTABLE","n":2624,"mean_r":-0.1110},
    "SNIPER|5": {"status":"UNSTABLE","n":5345,"mean_r":-0.0230},
    "SNIPER|6": {"status":"STABLE_NEGATIVE","n":3626,"mean_r":-0.2838},
    "SNIPER|7": {"status":"UNSTABLE","n":657,"mean_r":-0.0800},
}

H4 = {
    "MAIN|ALIGNED": {"status":"UNSTABLE","n":1112,"mean_r":0.0838},
    "MAIN|NEUTRAL": {"status":"UNSTABLE","n":282,"mean_r":-0.0368},
    "SNIPER|ALIGNED": {"status":"STABLE_NEGATIVE","n":5172,"mean_r":-0.0990},
    "SNIPER|COUNTER": {"status":"STABLE_NEGATIVE","n":4985,"mean_r":-0.1325},
    "SNIPER|NEUTRAL": {"status":"STABLE_NEGATIVE","n":3663,"mean_r":-0.1327},
}


def session_bucket(bar_datetime):
    minute = gigi_clock.local_minute(bar_datetime)
    if minute < 5*60 or minute >= 20*60:
        return "OUTSIDE"
    if minute < 10*60:
        return "EARLY_05_10"
    if minute < 13*60:
        return "LONDON_10_13"
    if minute < 15*60+20:
        return "MIDDAY_13_1520"
    if minute < 18*60:
        return "US_1520_18"
    return "LATE_18_20"


def h4_alignment(side, h4_bias):
    side = str(side or "").upper()
    bias = str(h4_bias or "NEUTRAL").upper()
    if side not in ("BUY","SELL") or bias == "NEUTRAL":
        return "NEUTRAL"
    if (side == "BUY" and bias == "UP") or (side == "SELL" and bias == "DOWN"):
        return "ALIGNED"
    return "COUNTER"


def _row(table, key):
    out = dict(table.get(key) or {})
    out["key"] = key
    if not out:
        out = {"key":key,"status":"UNKNOWN","n":0,"mean_r":0.0}
    return out


def assess(mode, side, bar_datetime, strength, h4_bias):
    mode = "MAIN" if str(mode or "").upper() == "MAIN" else "SNIPER"
    session = session_bucket(bar_datetime)
    align = h4_alignment(side, h4_bias)
    try:
        strength = int(strength)
    except Exception:
        strength = 0

    session_row = _row(SESSION, f"{mode}|{session}")
    strength_row = _row(STRENGTH, f"{mode}|{strength}")
    h4_row = _row(H4, f"{mode}|{align}")
    statuses = [session_row["status"], strength_row["status"], h4_row["status"]]

    if statuses.count("STABLE_NEGATIVE") >= 2:
        posture = "PERSISTENT_NEGATIVE_SLICE"
    elif "STABLE_NEGATIVE" in statuses:
        posture = "NEGATIVE_SLICE_CAUTION"
    elif all(s in ("UNSTABLE","INSUFFICIENT_PER_WINDOW","UNKNOWN") for s in statuses):
        means = [float(x.get("mean_r") or 0.0) for x in (session_row,strength_row,h4_row) if x.get("status")!="UNKNOWN"]
        posture = "PROMISING_UNSTABLE_SLICE" if means and sum(means)/len(means) > 0 else "UNPROVEN_SLICE"
    else:
        posture = "UNPROVEN_SLICE"

    return {
        "posture": posture,
        "mode": mode,
        "session_bucket": session,
        "strength": strength,
        "h4_alignment": align,
        "session_proof": session_row,
        "strength_proof": strength_row,
        "h4_proof": h4_row,
        "source": SOURCE,
        "external_historical_context_backfilled": False,
        "directional_signal": False,
        "execution_gate": False,
        "note": "granular_walkforward_context_not_live_authorization",
    }
