"""Gold setup-archetype classifier for Gigi shadow analysis.

This layer labels *what kind of trade idea* the market is presenting. It does
not choose a side, publish a signal, or alter risk. The goal is to stop very
different situations (trend continuation, liquidity reversal, event digestion,
range fade, squeeze) from being evaluated as if they were the same setup.
"""
from __future__ import annotations


def classify(
    signal=None,
    regime=None,
    liquidity=None,
    macro=None,
    event_response=None,
    crowding=None,
    session_profile=None,
    options=None,
    price_prior=None,
):
    signal = signal or {}
    regime = regime or {}
    liquidity = liquidity or {}
    macro = macro or {}
    event_response = event_response or {}
    crowding = crowding or {}
    session_profile = session_profile or {}
    options = options or {}
    price_prior = price_prior or {}

    side = str(signal.get("side") or "WAIT").upper()
    name = str(regime.get("name") or "UNKNOWN").upper()
    h4 = str(regime.get("h4_bias") or "NEUTRAL").upper()
    liq = str(liquidity.get("event") or "UNKNOWN").upper()
    macro_phase = str(macro.get("phase") or "NORMAL").upper()
    event_state = str(event_response.get("state") or "NO_ACTIVE_HIGH_EVENT").upper()
    crowd = str(crowding.get("dominant_risk") or "BALANCED").upper()
    vwap = str(session_profile.get("vwap_relation") or "UNKNOWN").upper()
    range_event = str(session_profile.get("range_event") or "UNKNOWN").upper()
    prior = str(price_prior.get("status") or price_prior.get("state") or "UNKNOWN").upper()
    options_pin = str(options.get("near_expiry_pin_state") or "UNKNOWN").upper()

    scores = {
        "TREND_CONTINUATION": 0,
        "BREAKOUT_ACCEPTANCE": 0,
        "LIQUIDITY_REVERSAL": 0,
        "EVENT_DIGESTION": 0,
        "SQUEEZE_LIQUIDATION": 0,
        "RANGE_MEAN_REVERSION": 0,
    }
    evidence = {k: [] for k in scores}

    # Trend continuation: aligned higher-timeframe direction + acceptance.
    if name in ("TREND_UP", "TREND_DOWN", "TREND_EXPANSION"):
        scores["TREND_CONTINUATION"] += 2
        evidence["TREND_CONTINUATION"].append("trend_regime")
    if (side == "BUY" and h4 == "UP") or (side == "SELL" and h4 == "DOWN"):
        scores["TREND_CONTINUATION"] += 2
        evidence["TREND_CONTINUATION"].append("h4_side_alignment")
    if (side == "BUY" and vwap == "ABOVE_ACCEPTANCE") or (side == "SELL" and vwap == "BELOW_ACCEPTANCE"):
        scores["TREND_CONTINUATION"] += 1
        evidence["TREND_CONTINUATION"].append("session_vwap_acceptance")

    # Accepted breakouts are distinct from generic trend continuation.
    if range_event in ("ACCEPTED_ABOVE", "ACCEPTED_BELOW"):
        scores["BREAKOUT_ACCEPTANCE"] += 3
        evidence["BREAKOUT_ACCEPTANCE"].append("session_range_acceptance")
    if (side == "BUY" and range_event == "ACCEPTED_ABOVE") or (side == "SELL" and range_event == "ACCEPTED_BELOW"):
        scores["BREAKOUT_ACCEPTANCE"] += 2
        evidence["BREAKOUT_ACCEPTANCE"].append("acceptance_matches_side")

    # Liquidity reversal: sweep/failure in the opposite direction of the entry.
    if liq in ("BUY_SIDE_SWEEP", "SELL_SIDE_SWEEP", "TWO_SIDED_SWEEP"):
        scores["LIQUIDITY_REVERSAL"] += 2
        evidence["LIQUIDITY_REVERSAL"].append("liquidity_sweep")
    if (side == "BUY" and liq == "SELL_SIDE_SWEEP") or (side == "SELL" and liq == "BUY_SIDE_SWEEP"):
        scores["LIQUIDITY_REVERSAL"] += 3
        evidence["LIQUIDITY_REVERSAL"].append("sweep_reversal_matches_side")
    if range_event in ("FAILED_BREAK_ABOVE", "FAILED_BREAK_BELOW"):
        scores["LIQUIDITY_REVERSAL"] += 1
        evidence["LIQUIDITY_REVERSAL"].append("failed_session_break")

    # Event digestion: post-release confirmation/reversal after the first spike.
    if macro_phase in ("HIGH_EVENT_DIGESTION_5_15M", "MEDIUM_EVENT_DIGESTION_5_15M"):
        scores["EVENT_DIGESTION"] += 3
        evidence["EVENT_DIGESTION"].append("post_event_digestion_window")
    if event_state in ("SHOCK_REVERSED", "SHOCK_CONFIRMED", "SHOCK_PARTIALLY_RETRACED"):
        scores["EVENT_DIGESTION"] += 2
        evidence["EVENT_DIGESTION"].append("measured_event_response")
    if macro_phase in ("HIGH_EVENT_SHOCK_0_5M", "MEDIUM_EVENT_SHOCK_0_5M"):
        scores["EVENT_DIGESTION"] -= 2
        evidence["EVENT_DIGESTION"].append("first_spike_not_digestion")

    # Squeeze/liquidation is a special acceleration archetype.
    if crowd in ("HIGH_LONG_LIQUIDATION", "HIGH_SHORT_SQUEEZE"):
        # A confirmed high unwind state is structurally different from an
        # ordinary trend continuation, so it must outrank a plain trend label.
        scores["SQUEEZE_LIQUIDATION"] += 5
        evidence["SQUEEZE_LIQUIDATION"].append("high_crowding_unwind_risk")
    elif crowd in ("WATCH_LONG_LIQUIDATION", "WATCH_SHORT_SQUEEZE", "LONG_LIQUIDATION_BIAS", "SHORT_SQUEEZE_BIAS"):
        scores["SQUEEZE_LIQUIDATION"] += 2
        evidence["SQUEEZE_LIQUIDATION"].append("crowding_unwind_watch")
    if options_pin in ("NEAR_EXPIRY_OI_CLUSTER_AT_SPOT", "NEAR_EXPIRY_OI_CLUSTER_NEAR_SPOT"):
        # Pinning can suppress or distort follow-through, so it is evidence *against*
        # treating an ordinary move as a clean squeeze.
        scores["SQUEEZE_LIQUIDATION"] -= 1
        evidence["SQUEEZE_LIQUIDATION"].append("near_expiry_pin_caution")

    # Range mean reversion: only when the environment actually looks rangey.
    if name == "RANGE":
        scores["RANGE_MEAN_REVERSION"] += 3
        evidence["RANGE_MEAN_REVERSION"].append("range_regime")
    if vwap == "CROSSING":
        scores["RANGE_MEAN_REVERSION"] += 1
        evidence["RANGE_MEAN_REVERSION"].append("vwap_crossing")
    if range_event in ("FAILED_BREAK_ABOVE", "FAILED_BREAK_BELOW"):
        scores["RANGE_MEAN_REVERSION"] += 2
        evidence["RANGE_MEAN_REVERSION"].append("failed_range_break")
    if prior in ("LOW_BASE_RATE", "RARE_SETUP"):
        scores["RANGE_MEAN_REVERSION"] -= 1
        evidence["RANGE_MEAN_REVERSION"].append("price_prior_caution")

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary, primary_score = ordered[0]
    secondary, secondary_score = ordered[1]

    if primary_score < 3:
        primary = "NO_CLEAR_ARCHETYPE"
    if secondary_score < 3:
        secondary = None

    conflict = bool(
        primary != "NO_CLEAR_ARCHETYPE"
        and secondary
        and abs(primary_score - secondary_score) <= 1
    )

    return {
        "primary": primary,
        "primary_score": int(primary_score),
        "secondary": secondary,
        "secondary_score": int(secondary_score),
        "mixed_archetype": conflict,
        "evidence": evidence.get(primary, []) if primary in evidence else [],
        "all_scores": {k: int(v) for k, v in scores.items()},
        "directional_signal": False,
        "note": "setup_archetype_not_probability",
    }
