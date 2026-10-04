"""Contradiction-first thesis audit for Gigi shadow analysis.

Purpose: actively search for evidence against the proposed trade so confirmation
bias cannot hide behind a strong-looking technical score. Shadow only.
"""
from __future__ import annotations


def audit(signal, regime=None, intermarket=None, macro=None, liquidity=None,
          positioning=None, etf=None, crowding=None, options=None, yields=None,
          quality=None, execution_quality=None, exposure=None, event_response=None,
          usd_basket=None):
    signal=signal or {}
    regime=regime or {}
    intermarket=intermarket or {}
    macro=macro or {}
    liquidity=liquidity or {}
    positioning=positioning or {}
    etf=etf or {}
    crowding=crowding or {}
    options=options or {}
    yields=yields or {}
    quality=quality or {}
    execution_quality=execution_quality or {}
    exposure=exposure or {}
    event_response=event_response or {}
    usd_basket=usd_basket or {}

    side=str(signal.get("side") or "WAIT").upper()
    support=[]
    conflicts=[]
    uncertainty=[]

    h4=str(regime.get("h4_bias") or "NEUTRAL").upper()
    inter=str(intermarket.get("bias") or "NEUTRAL").upper()
    inter_relationship=str(intermarket.get("relationship_state") or "WEAK").upper()
    liq=str(liquidity.get("pressure") or "NEUTRAL").upper()
    pos=str(positioning.get("regime") or "UNKNOWN").upper()
    etf_regime=str(etf.get("regime") or "UNKNOWN").upper()
    macro_regime=str(macro.get("regime") or "UNKNOWN").upper()
    crowd=str(crowding.get("dominant_risk") or "BALANCED").upper()
    skew=str(options.get("skew") or "UNKNOWN").upper()

    def vote(condition_support, condition_conflict, name):
        if condition_support:
            support.append(name)
        elif condition_conflict:
            conflicts.append(name)

    if side=="BUY":
        vote(h4=="UP", h4=="DOWN", "h4_structure")
        vote(inter=="BULLISH_GOLD", inter=="BEARISH_GOLD", "intermarket")
        vote(liq=="BULLISH", liq=="BEARISH", "liquidity")
        vote(pos in ("LONG_BIASED_ADDING","SHORT_BIASED_COVERING"),
             pos=="SHORT_BIASED_ADDING", "positioning")
        vote(etf_regime=="BROAD_INFLOW", etf_regime=="BROAD_OUTFLOW", "etf_flow")
        if crowd in ("HIGH_LONG_LIQUIDATION","WATCH_LONG_LIQUIDATION","LONG_LIQUIDATION_BIAS"):
            conflicts.append("crowding_liquidation")
    elif side=="SELL":
        vote(h4=="DOWN", h4=="UP", "h4_structure")
        vote(inter=="BEARISH_GOLD", inter=="BULLISH_GOLD", "intermarket")
        vote(liq=="BEARISH", liq=="BULLISH", "liquidity")
        vote(pos in ("SHORT_BIASED_ADDING","LONG_BIASED_DELEVERAGING"),
             pos=="LONG_BIASED_ADDING", "positioning")
        vote(etf_regime=="BROAD_OUTFLOW", etf_regime=="BROAD_INFLOW", "etf_flow")
        if crowd in ("HIGH_SHORT_SQUEEZE","WATCH_SHORT_SQUEEZE","SHORT_SQUEEZE_BIAS"):
            conflicts.append("crowding_squeeze")
    else:
        uncertainty.append("no_directional_signal")

    event_state=str(event_response.get("state") or "NO_ACTIVE_HIGH_EVENT").upper()
    event_impulse=str(event_response.get("impulse") or "NONE").upper()
    if event_state=="FIRST_SPIKE_UNTRUSTED":
        uncertainty.append("event_first_spike_untrusted")
    elif event_state=="SHOCK_REVERSED":
        uncertainty.append("event_shock_reversed")
    elif event_state=="SHOCK_PARTIALLY_RETRACED":
        uncertainty.append("event_shock_partially_retraced")
    elif event_state=="SHOCK_CONFIRMED":
        uncertainty.append("event_shock_confirmed_"+event_impulse.lower())

    if macro_regime=="HIGH_IMPACT_WINDOW":
        uncertainty.append("high_impact_event_window")
    elif macro_regime=="UNKNOWN":
        uncertainty.append("macro_unknown")

    macro_bundle=str(macro.get("event_bundle_state") or "NONE").upper()
    macro_horizon=str(macro.get("calendar_horizon") or "UNKNOWN").upper()
    if macro_horizon=="EXHAUSTED":
        uncertainty.append("macro_calendar_horizon_exhausted")
    if macro_bundle=="MULTI_HIGH_RELEASE":
        uncertainty.append("macro_multi_high_release_bundle")
    elif macro_bundle=="MULTI_RELEASE":
        uncertainty.append("macro_multi_release_bundle")

    if inter_relationship=="FLIPPING_PRESENT":
        uncertainty.append("intermarket_relationship_flipping")
    elif inter_relationship=="SHORT_ONLY_PRESENT":
        uncertainty.append("intermarket_relationship_short_only")

    if etf_regime.startswith("MIXED"):
        uncertainty.append("etf_regional_rotation")

    usd_state=str(usd_basket.get("state") or "UNKNOWN").upper()
    usd_breadth=float(usd_basket.get("breadth") or 0.0)
    usd_relationship=str((usd_basket.get("gold_relationship") or {}).get("state") or "UNKNOWN").upper()
    if usd_relationship=="RELATIONSHIP_FLIP":
        uncertainty.append("gold_usd_relationship_flip")
    elif usd_relationship=="DECOUPLED_POSITIVE":
        uncertainty.append("gold_usd_positive_decoupling")
    if side=="BUY" and usd_state in ("USD_STRONG_IMPULSE","USD_FIRM"):
        uncertainty.append("synthetic_usd_headwind")
    elif side=="SELL" and usd_state in ("USD_WEAK_IMPULSE","USD_SOFT"):
        uncertainty.append("synthetic_usd_tailwind_against_sell")
    if usd_state in ("USD_STRONG_IMPULSE","USD_WEAK_IMPULSE") and usd_breadth >= 0.65:
        uncertainty.append("synthetic_usd_broad_impulse")

    real_yield_regime=str(yields.get("real_yield_regime") or "UNKNOWN").upper()
    if side=="BUY" and real_yield_regime=="RISING_REAL_YIELD":
        uncertainty.append("real_yield_headwind")
    elif side=="SELL" and real_yield_regime=="FALLING_REAL_YIELD":
        uncertainty.append("real_yield_tailwind_against_sell")
    elif real_yield_regime=="STALE":
        uncertainty.append("real_yield_data_stale")

    if skew=="DOWNSIDE_HEDGE_BID":
        uncertainty.append("options_downside_hedging")
    elif skew=="UPSIDE_CALL_BID":
        uncertainty.append("options_upside_call_demand")

    oi_state=str(options.get("oi_state") or "UNKNOWN").upper()
    gamma_context=str(options.get("gross_gamma_oi_context") or "UNKNOWN").upper()
    if oi_state=="PUT_HEAVY":
        uncertainty.append("options_put_oi_heavy")
    elif oi_state=="CALL_HEAVY":
        uncertainty.append("options_call_oi_heavy")
    if gamma_context=="HIGH_NEAR_SPOT_CONVEXITY":
        uncertainty.append("options_near_spot_convexity_high")
    elif gamma_context=="MODERATE_NEAR_SPOT_CONVEXITY":
        uncertainty.append("options_near_spot_convexity_moderate")

    execution_state=str(execution_quality.get("quality") or "UNKNOWN").upper()
    if execution_state in ("WIDE","EXTREME"):
        uncertainty.append("broker_spread_"+execution_state.lower())
    elif execution_state=="STALE_TICK":
        uncertainty.append("broker_tick_stale")
    elif execution_state=="BLOCKED_TERMINAL":
        uncertainty.append("terminal_autotrading_off")

    stacking_state=str(exposure.get("stacking_state") or "CLEAR").upper()
    book_state=str(exposure.get("book_state") or "FLAT").upper()
    if stacking_state=="HIGH_CONCENTRATION":
        uncertainty.append("same_direction_exposure_high")
    elif stacking_state=="CONCENTRATED":
        uncertainty.append("same_direction_exposure_concentrated")
    elif stacking_state=="LAYERED":
        uncertainty.append("same_direction_exposure_layered")
    if book_state=="TWO_SIDED":
        uncertainty.append("two_sided_position_book")

    quality_state=str(quality.get("quality") or "UNKNOWN").upper()
    if quality_state=="LOW":
        uncertainty.append("external_context_low_quality")
    elif quality_state=="MEDIUM":
        uncertainty.append("external_context_partial")

    risk_distance=float(signal.get("risk_distance") or 0.0)
    invalidation_defined=risk_distance > 0
    if not invalidation_defined:
        conflicts.append("invalidation_missing")

    # Count independent evidence families, not raw indicators. Positioning,
    # ETF flows, options and crowding are related flow/positioning evidence and
    # must not masquerade as four independent confirmations.
    family_map={
        "h4_structure":"structure",
        "intermarket":"intermarket",
        "liquidity":"liquidity",
        "positioning":"flows",
        "etf_flow":"flows",
        "crowding_liquidation":"flows",
        "crowding_squeeze":"flows",
        "invalidation_missing":"risk",
    }
    support_families=sorted({family_map.get(x,x) for x in set(support)})
    conflict_families=sorted({family_map.get(x,x) for x in set(conflicts)})
    conflict_count=len(conflict_families)
    support_count=len(support_families)
    if conflict_count >= 2 or not invalidation_defined:
        state="FRAGILE"
    elif conflict_count == 1:
        state="MIXED"
    elif support_count >= 3:
        state="CLEAN"
    else:
        state="UNPROVEN"

    return {
        "state":state,
        "support_count":support_count,
        "conflict_count":conflict_count,
        "supports":sorted(set(support)),
        "conflicts":sorted(set(conflicts)),
        "support_families":support_families,
        "conflict_families":conflict_families,
        "support_evidence_count":len(set(support)),
        "conflict_evidence_count":len(set(conflicts)),
        "uncertainty":sorted(set(uncertainty)),
        "invalidation_defined":invalidation_defined,
        "note":"shadow_contradiction_audit_not_entry_gate",
    }
