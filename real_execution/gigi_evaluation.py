"""Conservative shadow-outcome evaluation for Gigi.

MAIN and SNIPER have different holding horizons. Stop/target touches resolve
early; otherwise the observation stays pending until its full evaluation
horizon is available. Same-bar stop+target ambiguity remains conservative
because gigi_replay counts the stop first.
"""
from __future__ import annotations

import gigi_replay

SNIPER_HORIZON_BARS = 12   # 60 minutes on M5
MAIN_HORIZON_BARS = 36     # 180 minutes on M5


def horizon_bars(mode):
    return MAIN_HORIZON_BARS if str(mode or "").upper() == "MAIN" else SNIPER_HORIZON_BARS


def evaluate(side, entry, risk_distance, target_r, future_rows, mode):
    rows = list(future_rows or [])
    horizon = horizon_bars(mode)
    if not rows:
        return {
            "resolved": False,
            "outcome": "PENDING",
            "bars": 0,
            "horizon_bars": horizon,
        }

    probe = gigi_replay.first_touch_outcome(
        side,
        entry,
        risk_distance,
        target_r,
        rows,
        max_bars=min(len(rows), horizon),
    )

    # A stop or target is definitive even before the full horizon elapses.
    if probe.get("outcome") in ("STOP", "TARGET"):
        return {**probe, "horizon_bars": horizon}

    # A horizon close is not final until the full mode-specific window exists.
    if len(rows) < horizon:
        return {
            "resolved": False,
            "outcome": "PENDING",
            "bars": len(rows),
            "horizon_bars": horizon,
            "mfe_r": probe.get("mfe_r"),
            "mae_r": probe.get("mae_r"),
        }

    final = gigi_replay.first_touch_outcome(
        side,
        entry,
        risk_distance,
        target_r,
        rows,
        max_bars=horizon,
    )
    return {**final, "horizon_bars": horizon}
