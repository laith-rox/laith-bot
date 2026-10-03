"""Fuse Gigi shadow-analysis layers into an explainable context score.

This is not a win probability and it never sends an order. It only summarizes
whether regime, intermarket and macro context support or contradict the
technical setup.
"""
from __future__ import annotations


def evaluate(side, regime, intermarket, macro, liquidity=None, positioning=None, volatility=None, etf=None, crowding=None, options=None, yields=None, event_response=None, session_profile=None, benchmark=None, target_geometry=None):
    side=str(side or "WAIT").upper()
    regime=regime or {}
    intermarket=intermarket or {}
    macro=macro or {}
    liquidity=liquidity or {}
    positioning=positioning or {}
    volatility=volatility or {}
    etf=etf or {}
    crowding=crowding or {}
    options=options or {}
    yields=yields or {}
    event_response=event_response or {}
    session_profile=session_profile or {}
    benchmark=benchmark or {}
    target_geometry=target_geometry or {}

    score=0
    reasons=[]

    name=str(regime.get("name") or "UNKNOWN").upper()
    h4=str(regime.get("h4_bias") or "NEUTRAL").upper()
    effort=str(regime.get("effort_result") or "UNKNOWN").upper()

    if side=="BUY":
        if h4=="UP":
            score+=2; reasons.append("h4_regime_supports_buy")
        elif h4=="DOWN":
            score-=2; reasons.append("h4_regime_conflicts_buy")
    elif side=="SELL":
        if h4=="DOWN":
            score+=2; reasons.append("h4_regime_supports_sell")
        elif h4=="UP":
            score-=2; reasons.append("h4_regime_conflicts_sell")

    if name in ("VOLATILE_TRANSITION","TRANSITION"):
        score-=1
        reasons.append("transition_regime")
    elif name=="RANGE":
        reasons.append("range_regime")

    if effort=="ABSORPTION":
        reasons.append("effort_result_absorption")
    elif effort=="EXPANSION_CONFIRMED":
        score+=1
        reasons.append("effort_result_expansion")

    inter_relationship=str(intermarket.get("relationship_state") or "WEAK").upper()
    if inter_relationship=="FLIPPING_PRESENT":
        reasons.append("intermarket_relationship_flipping")
    elif inter_relationship=="SHORT_ONLY_PRESENT":
        reasons.append("intermarket_relationship_short_only")

    inter_bias=str(intermarket.get("bias") or "NEUTRAL").upper()
    if side=="BUY":
        if inter_bias=="BULLISH_GOLD":
            score+=1; reasons.append("intermarket_supports_buy")
        elif inter_bias=="BEARISH_GOLD":
            score-=1; reasons.append("intermarket_conflicts_buy")
    elif side=="SELL":
        if inter_bias=="BEARISH_GOLD":
            score+=1; reasons.append("intermarket_supports_sell")
        elif inter_bias=="BULLISH_GOLD":
            score-=1; reasons.append("intermarket_conflicts_sell")

    liquidity_pressure=str(liquidity.get("pressure") or "NEUTRAL").upper()
    liquidity_event=str(liquidity.get("event") or "UNKNOWN").upper()
    if side=="BUY":
        if liquidity_pressure=="BULLISH":
            score+=1; reasons.append("liquidity_supports_buy")
        elif liquidity_pressure=="BEARISH":
            score-=1; reasons.append("liquidity_conflicts_buy")
    elif side=="SELL":
        if liquidity_pressure=="BEARISH":
            score+=1; reasons.append("liquidity_supports_sell")
        elif liquidity_pressure=="BULLISH":
            score-=1; reasons.append("liquidity_conflicts_sell")
    if liquidity_event in ("BUY_SIDE_SWEEP","SELL_SIDE_SWEEP","TWO_SIDED_SWEEP"):
        reasons.append("liquidity_event:"+liquidity_event.lower())

    position_regime=str(positioning.get("regime") or "UNKNOWN").upper()
    positioning_crowding=str(positioning.get("crowding") or "UNKNOWN").upper()
    flow_vote=0
    if side=="BUY":
        if position_regime in ("LONG_BIASED_ADDING","SHORT_BIASED_COVERING"):
            flow_vote+=1; reasons.append("positioning_supports_buy")
        elif position_regime=="SHORT_BIASED_ADDING":
            flow_vote-=1; reasons.append("positioning_conflicts_buy")
        if positioning_crowding=="ELEVATED_LONG":
            flow_vote-=1; reasons.append("long_crowding_caution")
    elif side=="SELL":
        if position_regime in ("SHORT_BIASED_ADDING","LONG_BIASED_DELEVERAGING"):
            flow_vote+=1; reasons.append("positioning_supports_sell")
        elif position_regime=="LONG_BIASED_ADDING":
            flow_vote-=1; reasons.append("positioning_conflicts_sell")
        if positioning_crowding=="ELEVATED_SHORT":
            flow_vote-=1; reasons.append("short_crowding_caution")

    macro_regime=str(macro.get("regime") or "UNKNOWN").upper()
    macro_phase=str(macro.get("phase") or "NORMAL").upper()
    if macro_regime=="HIGH_IMPACT_WINDOW":
        score-=2
        reasons.append("high_impact_usd_window")
        if macro_phase=="HIGH_EVENT_SHOCK_0_5M":
            reasons.append("first_spike_untrusted")
        elif macro_phase=="HIGH_EVENT_DIGESTION_5_15M":
            reasons.append("post_event_price_discovery")
        elif macro_phase=="PRE_HIGH_EVENT":
            reasons.append("pre_event_positioning")
        market_state="EVENT_DRIVEN"
    elif macro_regime=="MEDIUM_IMPACT_WINDOW":
        score-=1
        reasons.append("medium_impact_usd_window")
        market_state="EVENT_AWARE"
    elif macro_regime=="UNKNOWN":
        reasons.append("macro_unknown")
        market_state="UNKNOWN_MACRO"
    else:
        market_state="NORMAL"

    etf_regime=str(etf.get("regime") or "UNKNOWN").upper()
    if side=="BUY":
        if etf_regime=="BROAD_INFLOW":
            flow_vote+=1; reasons.append("etf_flows_support_buy")
        elif etf_regime=="BROAD_OUTFLOW":
            flow_vote-=1; reasons.append("etf_flows_conflict_buy")
    elif side=="SELL":
        if etf_regime=="BROAD_OUTFLOW":
            flow_vote+=1; reasons.append("etf_flows_support_sell")
        elif etf_regime=="BROAD_INFLOW":
            flow_vote-=1; reasons.append("etf_flows_conflict_sell")
    if etf_regime.startswith("MIXED"):
        reasons.append("etf_flows_mixed")

    # CFTC positioning, ETF flows and positioning crowding are one related
    # evidence family. They may confirm each other, but cannot stack multiple
    # score points and masquerade as independent evidence.
    flow_family_score=1 if flow_vote>0 else (-1 if flow_vote<0 else 0)
    score+=flow_family_score
    if flow_vote==0 and (
        position_regime!="UNKNOWN" or etf_regime!="UNKNOWN" or positioning_crowding!="UNKNOWN"
    ):
        reasons.append("flow_family_mixed")

    volatility_state=str(volatility.get("state") or "UNKNOWN").upper()
    if volatility_state=="STRESS_EXPANSION":
        reasons.append("volatility_stress_expansion")
    elif volatility_state=="PRICED_MOVE_COMPRESSION":
        reasons.append("options_price_move_before_realized_expansion")
    elif volatility_state=="IMPLIED_ELEVATED":
        reasons.append("options_implied_vol_elevated")
    elif volatility_state=="REALIZED_EXPANSION":
        reasons.append("realized_vol_expanding")
    elif volatility_state=="REALIZED_COMPRESSION":
        reasons.append("realized_vol_compressed")

    options_skew=str(options.get("skew") or "UNKNOWN").upper()
    options_oi=str(options.get("oi_state") or "UNKNOWN").upper()
    options_gamma=str(options.get("gross_gamma_oi_context") or "UNKNOWN").upper()
    options_term=str(options.get("term_structure") or "UNKNOWN").upper()
    if options_skew=="DOWNSIDE_HEDGE_BID":
        reasons.append("options_downside_hedge_bid")
    elif options_skew=="UPSIDE_CALL_BID":
        reasons.append("options_upside_call_bid")
    if options_oi=="PUT_HEAVY":
        reasons.append("options_put_oi_heavy")
    elif options_oi=="CALL_HEAVY":
        reasons.append("options_call_oi_heavy")
    if options_gamma=="HIGH_NEAR_SPOT_CONVEXITY":
        reasons.append("options_high_near_spot_convexity")
    elif options_gamma=="MODERATE_NEAR_SPOT_CONVEXITY":
        reasons.append("options_moderate_near_spot_convexity")
    if options_term=="BACKWARDATION":
        reasons.append("options_near_term_vol_premium")
    elif options_term=="CONTANGO":
        reasons.append("options_far_term_vol_premium")

    real_yield_regime=str(yields.get("real_yield_regime") or "UNKNOWN").upper()
    policy_regime=str(yields.get("policy_regime") or "UNKNOWN").upper()
    if real_yield_regime=="RISING_REAL_YIELD":
        reasons.append("real_yield_headwind_gold")
    elif real_yield_regime=="FALLING_REAL_YIELD":
        reasons.append("real_yield_tailwind_gold")
    elif real_yield_regime=="STALE":
        reasons.append("real_yield_data_stale")
    if policy_regime=="RISING_FRONT_END":
        reasons.append("front_end_yields_rising")
    elif policy_regime=="FALLING_FRONT_END":
        reasons.append("front_end_yields_falling")

    event_state=str(event_response.get("state") or "NO_ACTIVE_HIGH_EVENT").upper()
    event_impulse=str(event_response.get("impulse") or "NONE").upper()
    if event_state=="FIRST_SPIKE_UNTRUSTED":
        reasons.append("event_first_spike_untrusted")
    elif event_state=="SHOCK_REVERSED":
        reasons.append("event_shock_reversed")
    elif event_state=="SHOCK_CONFIRMED":
        reasons.append("event_shock_confirmed")
    elif event_state=="SHOCK_PARTIALLY_RETRACED":
        reasons.append("event_shock_partially_retraced")
    elif event_state=="MUTED_RESPONSE":
        reasons.append("event_response_muted")

    session_vwap=str(session_profile.get("vwap_relation") or "UNKNOWN").upper()
    session_extension=str(session_profile.get("extension_state") or "UNKNOWN").upper()
    session_range_event=str(session_profile.get("range_event") or "UNKNOWN").upper()
    if session_vwap=="ABOVE_ACCEPTANCE":
        reasons.append("session_vwap_above_acceptance")
    elif session_vwap=="BELOW_ACCEPTANCE":
        reasons.append("session_vwap_below_acceptance")
    elif session_vwap=="CROSSING":
        reasons.append("session_vwap_crossing")
    if session_extension=="EXTENDED":
        reasons.append("session_vwap_extension")
    if session_range_event=="FAILED_BREAK_ABOVE":
        reasons.append("session_failed_break_above")
    elif session_range_event=="FAILED_BREAK_BELOW":
        reasons.append("session_failed_break_below")
    elif session_range_event=="ACCEPTED_ABOVE":
        reasons.append("session_range_acceptance_above")
    elif session_range_event=="ACCEPTED_BELOW":
        reasons.append("session_range_acceptance_below")

    benchmark_phase=str(benchmark.get("phase") or "UNKNOWN").upper()
    nearest_benchmark=str(benchmark.get("nearest_auction") or "UNKNOWN").upper()
    if benchmark_phase=="PRE_AUCTION":
        reasons.append("lbma_benchmark_pre_auction")
    elif benchmark_phase=="AUCTION_OR_IMMEDIATE_POST":
        reasons.append("lbma_benchmark_auction_window")

    target_geometry_state=str(target_geometry.get("state") or "UNKNOWN").upper()
    target_implied_relation=str(target_geometry.get("implied_move_relation") or "UNKNOWN").upper()
    if target_geometry_state=="AMBITION_HIGH":
        reasons.append("target_ambition_high")
    elif target_geometry_state=="AMBITION_ELEVATED":
        reasons.append("target_ambition_elevated")
    elif target_geometry_state=="SHORT_HORIZON":
        reasons.append("target_short_horizon")
    if target_implied_relation=="FAR_BEYOND_1D_PROXY":
        reasons.append("target_far_beyond_options_1d_proxy")

    options_skew=str(options.get("skew") or "UNKNOWN").upper()
    options_oi=str(options.get("oi_state") or "UNKNOWN").upper()
    if options_skew=="DOWNSIDE_HEDGE_BID":
        reasons.append("options_downside_hedge_bid")
    elif options_skew=="UPSIDE_CALL_BID":
        reasons.append("options_upside_call_bid")
    if options_oi=="PUT_HEAVY":
        reasons.append("options_put_oi_heavy")
    elif options_oi=="CALL_HEAVY":
        reasons.append("options_call_oi_heavy")

    crowding_risk=str(crowding.get("dominant_risk") or "BALANCED").upper()
    if crowding_risk in ("HIGH_LONG_LIQUIDATION","WATCH_LONG_LIQUIDATION","LONG_LIQUIDATION_BIAS"):
        reasons.append("long_liquidation_risk")
    elif crowding_risk in ("HIGH_SHORT_SQUEEZE","WATCH_SHORT_SQUEEZE","SHORT_SQUEEZE_BIAS"):
        reasons.append("short_squeeze_risk")

    if score>=3:
        alignment="STRONG_SUPPORT"
    elif score>=1:
        alignment="SUPPORT"
    elif score<=-3:
        alignment="STRONG_CONFLICT"
    elif score<=-1:
        alignment="CONFLICT"
    else:
        alignment="MIXED"

    return {
        "alignment": alignment,
        "score": int(score),
        "market_state": market_state,
        "volatility_state": volatility_state,
        "crowding_risk": crowding_risk,
        "options_skew": options_skew,
        "options_oi_state": options_oi,
        "options_gamma_context": options_gamma,
        "options_term_structure": options_term,
        "event_response_state": event_state,
        "event_impulse": event_impulse,
        "session_vwap_relation": session_vwap,
        "session_extension": session_extension,
        "session_range_event": session_range_event,
        "benchmark_phase": benchmark_phase,
        "nearest_benchmark": nearest_benchmark,
        "target_geometry_state": target_geometry_state,
        "target_implied_relation": target_implied_relation,
        "flow_family_score": int(flow_family_score),
        "reasons": reasons,
        "note": "alignment_score_not_probability",
    }
