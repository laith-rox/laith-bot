"""Crowding / liquidation-risk context for Gigi shadow analysis.

Combines slow positioning/ETF context with live volatility and liquidity clues.
It does not choose BUY/SELL and never sends orders. The purpose is to flag when
an apparently normal trend may actually be vulnerable to a squeeze or
liquidation cascade.
"""
from __future__ import annotations


def analyze(positioning=None, volatility=None, liquidity=None, etf=None, regime=None, options=None, flow_stress=None):
    positioning = positioning or {}
    volatility = volatility or {}
    liquidity = liquidity or {}
    etf = etf or {}
    regime = regime or {}
    options = options or {}
    flow_stress = flow_stress or {}

    long_risk = 0
    short_risk = 0
    reasons = []

    pos_regime = str(positioning.get("regime") or "UNKNOWN").upper()
    crowding = str(positioning.get("crowding") or "UNKNOWN").upper()
    vol_state = str(volatility.get("state") or "UNKNOWN").upper()
    liq_event = str(liquidity.get("event") or "UNKNOWN").upper()
    liq_pressure = str(liquidity.get("pressure") or "NEUTRAL").upper()
    etf_regime = str(etf.get("regime") or "UNKNOWN").upper()
    h4_bias = str(regime.get("h4_bias") or "NEUTRAL").upper()

    # Slow crowding / positioning backdrop.
    if crowding == "ELEVATED_LONG":
        long_risk += 2
        reasons.append("elevated_long_crowding")
    elif crowding == "ELEVATED_SHORT":
        short_risk += 2
        reasons.append("elevated_short_crowding")

    if pos_regime == "LONG_BIASED_DELEVERAGING":
        long_risk += 2
        reasons.append("managed_money_long_deleveraging")
    elif pos_regime == "SHORT_BIASED_COVERING":
        short_risk += 2
        reasons.append("managed_money_short_covering")
    elif pos_regime == "LONG_BIASED_ADDING":
        short_risk += 1
        reasons.append("managed_money_long_adding")
    elif pos_regime == "SHORT_BIASED_ADDING":
        long_risk += 1
        reasons.append("managed_money_short_adding")

    # Slow allocation flows.
    if etf_regime == "BROAD_OUTFLOW":
        long_risk += 2
        reasons.append("broad_etf_outflow")
    elif etf_regime == "MIXED_OUTFLOW":
        long_risk += 1
        reasons.append("mixed_etf_outflow")
    elif etf_regime == "BROAD_INFLOW":
        short_risk += 2
        reasons.append("broad_etf_inflow")
    elif etf_regime == "MIXED_INFLOW":
        short_risk += 1
        reasons.append("mixed_etf_inflow")

    # Options proxy cannot reveal customer/dealer sign. Skew may only
    # amplify a directional risk that already exists from independent evidence;
    # OI imbalance is recorded as context but never creates direction by itself.
    options_skew = str(options.get("skew") or "UNKNOWN").upper()
    options_oi = str(options.get("oi_state") or "UNKNOWN").upper()
    if options_skew == "DOWNSIDE_HEDGE_BID":
        reasons.append("options_downside_hedge_bid")
        if long_risk >= 2:
            long_risk += 1
            reasons.append("options_downside_hedge_confirms_existing_long_risk")
    elif options_skew == "UPSIDE_CALL_BID":
        reasons.append("options_upside_call_bid")
        if short_risk >= 2:
            short_risk += 1
            reasons.append("options_upside_call_confirms_existing_short_risk")
    if options_oi == "PUT_HEAVY":
        reasons.append("options_put_oi_heavy_unsigned")
    elif options_oi == "CALL_HEAVY":
        reasons.append("options_call_oi_heavy_unsigned")

    flow_state = str(flow_stress.get("state") or "UNKNOWN").upper()
    if flow_state == "DOWN_CASCADE":
        long_risk += 2
        reasons.append("m5_down_cascade")
    elif flow_state == "UP_SQUEEZE":
        short_risk += 2
        reasons.append("m5_up_squeeze")
    elif flow_state == "FAST_DOWN_IMPULSE":
        long_risk += 1
        reasons.append("m5_fast_down_impulse")
    elif flow_state == "FAST_UP_IMPULSE":
        short_risk += 1
        reasons.append("m5_fast_up_impulse")

    # Live trigger-like context: liquidity rejection and volatility expansion.
    if liq_event == "BUY_SIDE_SWEEP" or liq_pressure == "BEARISH":
        long_risk += 2
        reasons.append("bearish_liquidity_rejection")
    elif liq_event == "SELL_SIDE_SWEEP" or liq_pressure == "BULLISH":
        short_risk += 2
        reasons.append("bullish_liquidity_rejection")

    speed_gate = (
        vol_state in ("STRESS_EXPANSION", "REALIZED_EXPANSION")
        or flow_state in ("DOWN_CASCADE", "UP_SQUEEZE")
    )
    if speed_gate:
        long_risk += 1
        short_risk += 1
        reasons.append("volatility_speed_gate_open")
    elif vol_state == "PRICED_MOVE_COMPRESSION":
        reasons.append("options_priced_move_before_break")

    # Structure is context, not a trigger.
    if h4_bias == "DOWN":
        long_risk += 1
        reasons.append("h4_down_bias")
    elif h4_bias == "UP":
        short_risk += 1
        reasons.append("h4_up_bias")

    def classify(score, kind):
        if score >= 7 and speed_gate:
            return "HIGH_" + kind
        if score >= 4:
            return "WATCH_" + kind
        return "NORMAL"

    long_state = classify(long_risk, "LONG_LIQUIDATION")
    short_state = classify(short_risk, "SHORT_SQUEEZE")

    if long_risk >= short_risk + 3:
        dominant = long_state if long_state != "NORMAL" else "LONG_LIQUIDATION_BIAS"
    elif short_risk >= long_risk + 3:
        dominant = short_state if short_state != "NORMAL" else "SHORT_SQUEEZE_BIAS"
    else:
        dominant = "BALANCED"

    return {
        "long_liquidation_score": int(long_risk),
        "short_squeeze_score": int(short_risk),
        "long_state": long_state,
        "short_state": short_state,
        "dominant_risk": dominant,
        "speed_gate": bool(speed_gate),
        "reasons": reasons,
        "directional_signal": False,
        "note": "crowding_risk_context_not_entry_signal",
    }
