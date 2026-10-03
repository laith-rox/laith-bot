"""Crowding / liquidation-risk context for Gigi shadow analysis.

Combines slow positioning/ETF context with live volatility and liquidity clues.
It does not choose BUY/SELL and never sends orders. The purpose is to flag when
an apparently normal trend may actually be vulnerable to a squeeze or
liquidation cascade.
"""
from __future__ import annotations


def analyze(positioning=None, volatility=None, liquidity=None, etf=None, regime=None, options=None):
    positioning = positioning or {}
    volatility = volatility or {}
    liquidity = liquidity or {}
    etf = etf or {}
    regime = regime or {}
    options = options or {}

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

    # Options skew / OI are proxy context, not direction by themselves.
    options_skew = str(options.get("skew") or "UNKNOWN").upper()
    options_oi = str(options.get("oi_state") or "UNKNOWN").upper()
    if options_skew == "DOWNSIDE_HEDGE_BID":
        long_risk += 1
        reasons.append("options_downside_hedge_bid")
    elif options_skew == "UPSIDE_CALL_BID":
        short_risk += 1
        reasons.append("options_upside_call_bid")
    if options_oi == "PUT_HEAVY":
        long_risk += 1
        reasons.append("options_put_oi_heavy")
    elif options_oi == "CALL_HEAVY":
        short_risk += 1
        reasons.append("options_call_oi_heavy")

    # Options are sentiment/hedging context only. They can amplify a squeeze/liquidation
    # hypothesis but never create one by themselves.
    options_skew = str(options.get("skew") or "UNKNOWN").upper()
    options_oi = str(options.get("oi_state") or "UNKNOWN").upper()
    if options_skew == "DOWNSIDE_HEDGE_BID":
        long_risk += 1
        reasons.append("options_downside_hedge_bid")
    elif options_skew == "UPSIDE_CALL_BID":
        short_risk += 1
        reasons.append("options_upside_call_bid")
    if options_oi == "PUT_HEAVY":
        long_risk += 1
        reasons.append("options_put_oi_heavy")
    elif options_oi == "CALL_HEAVY":
        short_risk += 1
        reasons.append("options_call_oi_heavy")

    # Live trigger-like context: liquidity rejection and volatility expansion.
    if liq_event == "BUY_SIDE_SWEEP" or liq_pressure == "BEARISH":
        long_risk += 2
        reasons.append("bearish_liquidity_rejection")
    elif liq_event == "SELL_SIDE_SWEEP" or liq_pressure == "BULLISH":
        short_risk += 2
        reasons.append("bullish_liquidity_rejection")

    speed_gate = vol_state in ("STRESS_EXPANSION", "REALIZED_EXPANSION")
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
