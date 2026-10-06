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
    "requested_mode",
    "regime",
    "alignment",
    "context_score_bucket",
    "macro_regime",
    "macro_phase",
    "macro_event_class",
    "macro_event_bundle",
    "macro_calendar_horizon",
    "event_response_state",
    "event_impulse",
    "macro_surprise_bundle",
    "macro_surprise_price_relation",
    "intermarket_bias",
    "intermarket_relationship_state",
    "usd_basket_state",
    "usd_gold_relationship",
    "usd_breadth_bucket",
    "liquidity_event",
    "positioning_regime",
    "positioning_crowding",
    "volatility_state",
    "gvz_regime",
    "etf_regime",
    "etf_breadth",
    "central_bank_regime",
    "crowding_risk",
    "options_skew",
    "options_oi_state",
    "options_gamma_context",
    "options_term_structure",
    "options_expiry_pin_state",
    "real_yield_regime",
    "policy_regime",
    "stop_geometry",
    "stop_noise_exposure",
    "thesis_state",
    "data_quality",
    "execution_quality",
    "spread_atr_bucket",
    "exposure_stacking",
    "exposure_book",
    "behavior_state",
    "readiness_state",
    "session_vwap_relation",
    "session_extension",
    "session_range_event",
    "session_profile_quality",
    "benchmark_phase",
    "benchmark_name",
    "target_geometry_state",
    "target_implied_relation",
    "price_prior_status",
    "market_proof_state",
    "market_proof_mode_status",
    "setup_archetype",
    "setup_mixed",
    "evidence_state",
    "evidence_support_count",
    "evidence_conflict_count",
    "evidence_price_family",
    "evidence_macro_family",
    "evidence_flow_family",
    "evidence_options_family",
    "evidence_cross_family",
    "china_premium_state",
    "india_premium_state",
    "session",
    "strength",
)


def context_score_bucket(score):
    """Coarse bucket for calibration; the raw alignment score is not a probability."""
    try:
        value = int(score)
    except Exception:
        return "UNKNOWN"
    if value >= 3:
        return "POS_STRONG"
    if value >= 1:
        return "POS"
    if value <= -3:
        return "NEG_STRONG"
    if value <= -1:
        return "NEG"
    return "ZERO"


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


def validated_shadow_weight(state, validation_report, dimension, value, drift_report=None):
    """Return a shadow weight only after stability and drift checks pass.

    This never changes execution. It prevents an in-sample average from being
    treated as learned when the later out-of-sample segment flips sign, and
    can additionally suppress a previously stable bucket whose recent regime
    has drifted.
    """
    key=_bucket_key(dimension,value)
    validation=(validation_report or {}).get("buckets",{}).get(key,{})
    status=str(validation.get("status") or "")
    if status not in ("STABLE_POSITIVE","STABLE_NEGATIVE"):
        return 0.0
    if drift_report is not None:
        drift=(drift_report or {}).get("buckets",{}).get(key,{})
        if str(drift.get("status") or "") != "STABLE":
            return 0.0
        if drift.get("shadow_trust") is not True:
            return 0.0
    return shadow_weight(state,dimension,value)
