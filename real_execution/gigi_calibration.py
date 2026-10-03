"""Empirical calibration for Gigi shadow learning.

Turns resolved shadow observations into uncertainty-aware empirical outcome
rates. It never treats the alignment score itself as a probability and never
changes execution parameters.
"""
from __future__ import annotations

import math

MIN_CALIBRATION_SAMPLES = 30
MAX_WILSON_WIDTH = 0.35


def wilson_interval(wins, n, z=1.96):
    n = int(n or 0)
    wins = int(wins or 0)
    if n <= 0:
        return (0.0, 1.0)
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def calibrate_bucket(bucket):
    bucket = bucket or {}
    n = int(bucket.get("n") or 0)
    wins = int(bucket.get("wins") or 0)
    sum_r = float(bucket.get("sum_r") or 0.0)
    low, high = wilson_interval(wins, n)
    width = high - low
    empirical = (wins / n) if n else None
    mean_r = (sum_r / n) if n else None

    if n < MIN_CALIBRATION_SAMPLES:
        status = "INSUFFICIENT_SAMPLE"
    elif width > MAX_WILSON_WIDTH:
        status = "WIDE_UNCERTAINTY"
    else:
        status = "CALIBRATED_EMPIRICAL"

    return {
        "n": n,
        "status": status,
        "empirical_positive_rate": None if empirical is None else round(empirical, 4),
        "wilson_low": round(low, 4),
        "wilson_high": round(high, 4),
        "wilson_width": round(width, 4),
        "mean_r": None if mean_r is None else round(mean_r, 4),
        "note": "empirical_shadow_outcomes_not_forward_probability",
    }


def report(state, dimensions=None):
    state = state or {}
    buckets = state.get("buckets") or {}
    dims = tuple(dimensions or ("alignment", "context_score_bucket", "regime", "session"))
    selected = {}
    for key, bucket in sorted(buckets.items()):
        if ":" not in key:
            continue
        dim, _ = key.split(":", 1)
        if dim in dims:
            selected[key] = calibrate_bucket(bucket)
    return {
        "resolved": int(state.get("resolved") or 0),
        "minimum_samples": MIN_CALIBRATION_SAMPLES,
        "dimensions": list(dims),
        "buckets": selected,
        "note": "calibration_report_shadow_only_not_trade_probability",
    }
