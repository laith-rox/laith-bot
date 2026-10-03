"""Out-of-sample stability checks for Gigi shadow learning.

Chronological validation only. This module never changes execution weights.
It exists to catch overfitting: a bucket that looked good in the earlier
sample but failed in the later sample is labelled unstable rather than learned.
"""
from __future__ import annotations

MIN_TOTAL = 40
TEST_FRACTION = 0.35
CLIP_R = 5.0


def _clip(value):
    return max(-CLIP_R, min(CLIP_R, float(value)))


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _win_rate(values):
    return sum(v > 0 for v in values) / len(values) if values else 0.0


def validate_values(values):
    vals=[_clip(v) for v in values]
    n=len(vals)
    if n < MIN_TOTAL:
        return {
            "n":n,
            "status":"INSUFFICIENT_OUT_OF_SAMPLE",
            "train_n":0,
            "test_n":0,
            "shadow_candidate":False,
        }

    test_n=max(12, int(round(n * TEST_FRACTION)))
    test_n=min(test_n, n-20)
    split=n-test_n
    train=vals[:split]
    test=vals[split:]

    train_mean=_mean(train)
    test_mean=_mean(test)
    train_wr=_win_rate(train)
    test_wr=_win_rate(test)

    if train_mean > 0 and test_mean > 0:
        status="STABLE_POSITIVE"
        candidate=True
    elif train_mean < 0 and test_mean < 0:
        status="STABLE_NEGATIVE"
        candidate=False
    else:
        status="UNSTABLE_SIGN_FLIP"
        candidate=False

    return {
        "n":n,
        "status":status,
        "train_n":len(train),
        "test_n":len(test),
        "train_mean_r":round(train_mean,4),
        "test_mean_r":round(test_mean,4),
        "train_win_rate":round(train_wr,4),
        "test_win_rate":round(test_wr,4),
        "shadow_candidate":candidate,
        "note":"chronological_shadow_validation_no_auto_promotion",
    }


def report(observations, dimensions):
    observations=sorted(
        list(observations or []),
        key=lambda x: float(x.get("resolved_at") or x.get("time") or 0.0),
    )
    buckets={}
    for dimension in dimensions:
        grouped={}
        for obs in observations:
            value=str(obs.get(dimension) or "UNKNOWN").upper()
            grouped.setdefault(value,[]).append(float(obs.get("close_r") or 0.0))
        for value,values in grouped.items():
            buckets[f"{dimension}:{value}"]=validate_values(values)

    return {
        "resolved_observations":len(observations),
        "minimum_total_per_bucket":MIN_TOTAL,
        "test_fraction":TEST_FRACTION,
        "clip_r":CLIP_R,
        "buckets":buckets,
        "note":"out_of_sample_shadow_validation_only",
    }
