"""Shadow learning and calibration for Gigi.

No order placement, no automatic parameter mutation. The model only aggregates
resolved observations and withholds conclusions until each bucket has enough
samples. This keeps one lucky or unlucky trade from rewriting the strategy.
"""
from __future__ import annotations

MIN_BUCKET_SAMPLES = 20
MIN_WEIGHT_SAMPLES = 30
MAX_SHADOW_WEIGHT = 0.25

DIMENSIONS = (
    "mode",
    "regime",
    "alignment",
    "macro_regime",
    "macro_phase",
    "intermarket_bias",
    "liquidity_event",
    "positioning_regime",
    "positioning_crowding",
    "volatility_state",
    "gvz_regime",
    "etf_regime",
    "etf_breadth",
    "crowding_risk",
    "options_skew",
    "options_oi_state",
    "options_gamma_context",
    "real_yield_regime",
    "policy_regime",
    "stop_geometry",
    "stop_noise_exposure",
    "thesis_state",
    "data_quality",
    "execution_quality",
    "spread_atr_bucket",
    "session",
    "strength",
)


def new_state():
    return {"version": 1, "resolved": 0, "buckets": {}}


def _bucket_key(dimension, value):
    return f"{dimension}:{str(value or 'UNKNOWN').upper()}"


def _ensure(state, key):
    bucket = state["buckets"].setdefault(
        key,
        {"n": 0, "wins": 0, "sum_r": 0.0, "sum_r2": 0.0, "sum_mfe_r": 0.0, "sum_mae_r": 0.0},
    )
    return bucket


def record(state, observation):
    """Record one resolved shadow observation exactly once."""
    if state is None:
        state = new_state()
    if observation.get("resolved") is not True:
        raise ValueError("observation_must_be_resolved")
    if observation.get("id") in set(state.get("seen_ids") or []):
        return state

    close_r = float(observation.get("close_r") or 0.0)
    mfe_r = float(observation.get("mfe_r") or 0.0)
    mae_r = float(observation.get("mae_r") or 0.0)
    state["resolved"] = int(state.get("resolved") or 0) + 1
    seen = list(state.get("seen_ids") or [])
    seen.append(observation.get("id"))
    state["seen_ids"] = seen[-5000:]

    for dimension in DIMENSIONS:
        value = observation.get(dimension, "UNKNOWN")
        bucket = _ensure(state, _bucket_key(dimension, value))
        bucket["n"] += 1
        bucket["wins"] += int(close_r > 0)
        bucket["sum_r"] += close_r
        bucket["sum_r2"] += close_r * close_r
        bucket["sum_mfe_r"] += mfe_r
        bucket["sum_mae_r"] += mae_r
    return state


def summarize_bucket(bucket):
    n = int((bucket or {}).get("n") or 0)
    if n <= 0:
        return {"n": 0, "status": "NO_DATA"}
    mean_r = float(bucket.get("sum_r") or 0.0) / n
    win_rate = float(bucket.get("wins") or 0) / n
    mean_mfe = float(bucket.get("sum_mfe_r") or 0.0) / n
    mean_mae = float(bucket.get("sum_mae_r") or 0.0) / n
    return {
        "n": n,
        "status": "CALIBRATED" if n >= MIN_BUCKET_SAMPLES else "INSUFFICIENT_SAMPLE",
        "mean_r": round(mean_r, 4),
        "win_rate": round(win_rate, 4),
        "mean_mfe_r": round(mean_mfe, 4),
        "mean_mae_r": round(mean_mae, 4),
    }


def report(state):
    state = state or new_state()
    return {
        "resolved": int(state.get("resolved") or 0),
        "minimum_bucket_samples": MIN_BUCKET_SAMPLES,
        "minimum_weight_samples": MIN_WEIGHT_SAMPLES,
        "buckets": {k: summarize_bucket(v) for k, v in sorted((state.get("buckets") or {}).items())},
        "note": "shadow_learning_only_not_probability",
    }


def shadow_weight(state, dimension, value):
    """Bounded suggestion only; never changes execution parameters automatically."""
    bucket = (state or {}).get("buckets", {}).get(_bucket_key(dimension, value), {})
    n = int(bucket.get("n") or 0)
    if n < MIN_WEIGHT_SAMPLES:
        return 0.0
    mean_r = float(bucket.get("sum_r") or 0.0) / n
    return round(max(-MAX_SHADOW_WEIGHT, min(MAX_SHADOW_WEIGHT, mean_r / 4.0)), 4)
