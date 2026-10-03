"""Contradiction-first thesis audit for Gigi shadow analysis.

Purpose: actively search for evidence against the proposed trade so confirmation
bias cannot hide behind a strong-looking technical score. Shadow only.
"""
from __future__ import annotations


def audit(signal, regime=None, intermarket=None, macro=None, liquidity=None,
          positioning=None, etf=None, crowding=None, options=None, yields=None):
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

    side=str(signal.get("side") or "WAIT").upper()
    support=[]
    conflicts=[]
    uncertainty=[]

    h4=str(regime.get("h4_bias") or "NEUTRAL").upper()
    inter=str(intermarket.get("bias") or "NEUTRAL").upper()
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

    if macro_regime=="HIGH_IMPACT_WINDOW":
        uncertainty.append("high_impact_event_window")
    elif macro_regime=="UNKNOWN":
        uncertainty.append("macro_unknown")

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
