"""Historical price-only research prior for Gigi shadow analysis.

Derived from three non-overlapping 60-day MT5 walk-forward windows using the
current price/structure engine, historical broker spreads, and the current
candidate profit-protection policy replayed conservatively from the next bar.

External slow feeds (news, CFTC, ETF, options and yields) are excluded because
historical values were not reconstructed. This module is descriptive only. It
never blocks or promotes live execution.
"""
from __future__ import annotations

BASELINE = {
    "fast_primary_2of3": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":254,"mean_r":-0.1818},
            {"n":285,"mean_r":-0.2744},
            {"n":238,"mean_r":-0.2880},
        ],
    },
    "m15_resistance_break_retest": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":45,"mean_r":-0.0181},
            {"n":31,"mean_r":-0.0626},
            {"n":33,"mean_r":-0.4090},
        ],
    },
    "m15_support_break_retest": {
        "status":"STABLE_POSITIVE",
        "windows":[
            {"n":44,"mean_r":0.3229},
            {"n":59,"mean_r":0.0988},
            {"n":56,"mean_r":0.0180},
        ],
    },
    "mtf_countertrend_medium": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":108,"mean_r":-0.1907},
            {"n":79,"mean_r":-0.1489},
            {"n":53,"mean_r":-0.1887},
        ],
    },
    "mtf_medium_continuation": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":304,"mean_r":-0.0798},
            {"n":278,"mean_r":-0.0490},
            {"n":280,"mean_r":-0.1604},
        ],
    },
    "sniper_strength_stop_cap": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":1082,"mean_r":-0.0123},
            {"n":986,"mean_r":-0.0612},
            {"n":1239,"mean_r":-0.0304},
        ],
    },
    "technical_medium_local_invalidation": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":330,"mean_r":-0.3838},
            {"n":349,"mean_r":-0.4015},
            {"n":388,"mean_r":-0.5378},
        ],
    },
    "technical_medium_recovered": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":74,"mean_r":-0.3491},
            {"n":76,"mean_r":-0.3797},
            {"n":44,"mean_r":-0.5568},
        ],
    },
}

SOURCE = "three_non_overlapping_60d_mt5_price_only_walkforward_with_profit_protection"
MIN_PER_WINDOW = 20
WINDOW_COUNT = 3


def assess(reason):
    key=str(reason or "")
    row=BASELINE.get(key)
    if row is None:
        return {
            "status":"UNQUALIFIED_OR_UNKNOWN",
            "reason":key,
            "source":SOURCE,
            "directional_signal":False,
            "execution_gate":False,
        }
    windows=[dict(x) for x in row["windows"]]
    return {
        "status":row["status"],
        "reason":key,
        "total_n":sum(int(x["n"]) for x in windows),
        "mean_r_across_windows":round(sum(float(x["mean_r"]) for x in windows)/len(windows),4),
        "windows":windows,
        "source":SOURCE,
        "min_per_window":MIN_PER_WINDOW,
        "window_count":WINDOW_COUNT,
        "directional_signal":False,
        "execution_gate":False,
        "note":"historical_prior_requires_fresh_forward_confirmation",
    }
