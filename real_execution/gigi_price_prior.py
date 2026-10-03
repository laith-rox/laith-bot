"""Historical price-only research prior for Gigi shadow analysis.

Derived from three non-overlapping 60-day MT5 walk-forward windows using the
current price/structure engine, historical broker spreads, no external slow
feeds, and conservative same-bar stop-first resolution.

This module is descriptive only. It does not block or promote live execution.
Its purpose is to make prior evidence visible and to test whether it persists
in fresh forward observations.
"""
from __future__ import annotations

BASELINE = {
    "fast_primary_2of3": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":254,"mean_r":-0.2390},
            {"n":285,"mean_r":-0.2834},
            {"n":238,"mean_r":-0.3139},
        ],
    },
    "m15_support_break_retest": {
        "status":"STABLE_POSITIVE",
        "windows":[
            {"n":44,"mean_r":0.3144},
            {"n":59,"mean_r":0.1035},
            {"n":56,"mean_r":0.2091},
        ],
    },
    "mtf_countertrend_medium": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":108,"mean_r":-0.2665},
            {"n":79,"mean_r":-0.1865},
            {"n":53,"mean_r":-0.2534},
        ],
    },
    "mtf_medium_continuation": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":304,"mean_r":-0.1336},
            {"n":278,"mean_r":-0.1346},
            {"n":281,"mean_r":-0.2515},
        ],
    },
    "sniper_strength_stop_cap": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":1082,"mean_r":-0.0862},
            {"n":986,"mean_r":-0.0524},
            {"n":1238,"mean_r":-0.0742},
        ],
    },
    "technical_medium_local_invalidation": {
        "status":"STABLE_NEGATIVE",
        "windows":[
            {"n":330,"mean_r":-0.3870},
            {"n":349,"mean_r":-0.4073},
            {"n":388,"mean_r":-0.5415},
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

SOURCE = "three_non_overlapping_60d_mt5_price_only_walkforward"
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
