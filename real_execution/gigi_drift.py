"""Regime-drift checks for Gigi shadow learning.

Compares older and recent resolved observations inside each learning bucket.
Purpose: stop a once-useful pattern from being treated as permanent when its
recent behaviour deteriorates. Shadow only; never changes execution directly.
"""
from __future__ import annotations

MIN_TOTAL = 45
RECENT_N = 15
CLIP_R = 5.0


def _clip(value):
    return max(-CLIP_R, min(CLIP_R, float(value)))


def _mean(values):
    return sum(values)/len(values) if values else 0.0


def _win(values):
    return sum(v>0 for v in values)/len(values) if values else 0.0


def detect_values(values):
    vals=[_clip(v) for v in values]
    n=len(vals)
    if n < MIN_TOTAL:
        return {
            "n":n,
            "status":"INSUFFICIENT_DRIFT_SAMPLE",
            "recent_n":0,
            "prior_n":0,
            "shadow_trust":False,
        }
    recent=vals[-RECENT_N:]
    prior=vals[:-RECENT_N]
    prior_mean=_mean(prior)
    recent_mean=_mean(recent)
    delta=recent_mean-prior_mean

    if prior_mean*recent_mean < 0 and abs(delta) >= 0.25:
        status="SIGN_FLIP"
        trust=False
    elif prior_mean >= 0.15 and recent_mean <= 0.0:
        status="EDGE_DECAY"
        trust=False
    elif prior_mean <= -0.15 and recent_mean >= 0.0:
        status="NEGATIVE_EDGE_BROKEN"
        trust=False
    elif abs(delta) >= 0.50:
        status="MATERIAL_SHIFT"
        trust=False
    else:
        status="STABLE"
        trust=True

    return {
        "n":n,
        "status":status,
        "prior_n":len(prior),
        "recent_n":len(recent),
        "prior_mean_r":round(prior_mean,4),
        "recent_mean_r":round(recent_mean,4),
        "delta_mean_r":round(delta,4),
        "prior_win_rate":round(_win(prior),4),
        "recent_win_rate":round(_win(recent),4),
        "shadow_trust":trust,
        "note":"recent_vs_prior_shadow_drift_only",
    }


def report(observations, dimensions):
    rows=sorted(
        list(observations or []),
        key=lambda x:float(x.get("resolved_at") or x.get("time") or 0.0),
    )
    buckets={}
    for dimension in dimensions:
        grouped={}
        for obs in rows:
            value=str(obs.get(dimension) or "UNKNOWN").upper()
            grouped.setdefault(value,[]).append(float(obs.get("close_r") or 0.0))
        for value,values in grouped.items():
            buckets[f"{dimension}:{value}"]=detect_values(values)
    return {
        "resolved_observations":len(rows),
        "minimum_total_per_bucket":MIN_TOTAL,
        "recent_window":RECENT_N,
        "buckets":buckets,
        "note":"shadow_drift_detection_no_auto_execution_change",
    }
