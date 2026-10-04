"""Broker-price market-proof layer for Gigi shadow analysis.

Evidence source: six non-overlapping 60-day XAUUSD.m walk-forward windows
(2025-10-09 through 2026-10-04), historical broker spreads included and the
candidate profit-protection policy replayed conservatively.

This module is descriptive only. It does not authorize, block, size or place
orders. External historical macro/options/ETF/CFTC context was not backfilled.
"""
from __future__ import annotations

import gigi_price_prior

MODE_WINDOWS = {
    "MAIN": [
        {"n":258,"mean_r":0.0838},
        {"n":252,"mean_r":-0.0244},
        {"n":249,"mean_r":0.0831},
        {"n":170,"mean_r":0.1045},
        {"n":233,"mean_r":0.1152},
        {"n":232,"mean_r":0.0087},
    ],
    "SNIPER": [
        {"n":2345,"mean_r":-0.1034},
        {"n":2335,"mean_r":-0.1345},
        {"n":2404,"mean_r":-0.1422},
        {"n":2057,"mean_r":-0.1375},
        {"n":2315,"mean_r":-0.1424},
        {"n":2362,"mean_r":-0.0656},
    ],
}

SOURCE = "six_non_overlapping_60d_mt5_price_only_walkforward_20251009_20261004"


def _weighted(rows):
    n=sum(int(x["n"]) for x in rows)
    return n, (sum(int(x["n"])*float(x["mean_r"]) for x in rows)/n if n else 0.0)


def assess(mode, reason=None):
    mode=str(mode or "UNKNOWN").upper()
    rows=MODE_WINDOWS.get(mode,[])
    n,mean=_weighted(rows)
    signs=[1 if float(x["mean_r"])>0 else (-1 if float(x["mean_r"])<0 else 0) for x in rows]
    if rows and all(x<0 for x in signs):
        mode_status="STABLE_NEGATIVE"
    elif rows and all(x>0 for x in signs):
        mode_status="STABLE_POSITIVE"
    elif rows and mean>0:
        mode_status="PROMISING_UNSTABLE"
    elif rows:
        mode_status="NEGATIVE_UNSTABLE"
    else:
        mode_status="UNKNOWN"

    reason_prior=gigi_price_prior.assess(reason)
    reason_status=str(reason_prior.get("status") or "UNQUALIFIED_OR_UNKNOWN")
    if mode_status=="STABLE_NEGATIVE" or reason_status=="STABLE_NEGATIVE":
        proof_state="MARKET_PROVEN_CAUTION"
    elif mode_status=="STABLE_POSITIVE" and reason_status=="STABLE_POSITIVE":
        proof_state="MULTI_WINDOW_SUPPORT"
    elif mode_status=="PROMISING_UNSTABLE":
        proof_state="PROMISING_NOT_PROVEN"
    else:
        proof_state="UNPROVEN"

    return {
        "proof_state":proof_state,
        "mode":mode,
        "mode_status":mode_status,
        "mode_total_n":n,
        "mode_weighted_mean_r":round(mean,4),
        "mode_windows":[dict(x) for x in rows],
        "reason_status":reason_status,
        "reason":str(reason or ""),
        "source":SOURCE,
        "external_historical_context_backfilled":False,
        "execution_gate":False,
        "directional_signal":False,
        "note":"market_proof_shadow_only_no_order_authorization",
    }
