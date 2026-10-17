"""Second-generation tactical gold setup selector for Gigi SHADOW research.

The legacy SNIPER population is stable-negative in the current price-only
walk-forward. This module deliberately does NOT loosen that old engine. Instead
it defines a narrower, new tactical research candidate built around distinct
price archetypes and execution-cost geometry.

It never publishes, authorizes, sizes, or modifies an order.
"""
from __future__ import annotations


ALLOWED_ARCHETYPES = {
    "LIQUIDITY_REVERSAL",
    "BREAKOUT_ACCEPTANCE",
    "EVENT_DIGESTION",
    "SQUEEZE_LIQUIDATION",
}

# Retrospective broker-price filter study over the current 240d observation
# sample. This is descriptive, not forward proof and not a win probability.
PRICE_RESEARCH = {
    "BREAKOUT_ACCEPTANCE": {
        "n":59, "mean_r":-0.1360, "profit_factor":0.6951,
        "status":"RESEARCH_HOLD_NEGATIVE",
    },
    "LIQUIDITY_REVERSAL": {
        "n":8, "mean_r":0.1993, "profit_factor":1.7399,
        "status":"PROMISING_INSUFFICIENT_SAMPLE",
    },
}


def archetype_research(archetype):
    return dict(PRICE_RESEARCH.get(str(archetype or "").upper()) or {
        "n":0, "mean_r":None, "profit_factor":None, "status":"UNBACKFILLED",
    })


def _cost_ratio(signal, execution_quality):
    try:
        spread=float((execution_quality or {}).get("spread_usd"))
        risk=float((signal or {}).get("risk_distance"))
        if spread < 0 or risk <= 0:
            return None
        return spread/risk
    except Exception:
        return None


def _h4_relation(side, regime):
    side=str(side or "").upper()
    h4=str((regime or {}).get("h4_bias") or "NEUTRAL").upper()
    if h4=="NEUTRAL":
        return "NEUTRAL"
    if (side=="BUY" and h4=="UP") or (side=="SELL" and h4=="DOWN"):
        return "ALIGNED"
    return "COUNTER"


def price_only_assess(signal=None, setup=None, stop_geometry=None,
                      spread_to_risk=None, price_prior=None):
    """Historical-testable core of the new tactical design.

    Uses only price-derived setup geometry, H4 relation, technical checks and
    historical spread/risk cost. No current macro/options/ETF/CFTC value is
    allowed into this function, which avoids look-ahead in broker walk-forward.
    """
    signal=signal or {}
    setup=setup or {}
    stop_geometry=stop_geometry or {}
    price_prior=price_prior or {}

    side=str(signal.get("side") or "WAIT").upper()
    archetype=str(setup.get("primary") or "NO_CLEAR_ARCHETYPE").upper()
    setup_score=int(setup.get("primary_score") or 0)
    prior=str(price_prior.get("status") or "UNQUALIFIED_OR_UNKNOWN").upper()
    stop_noise=str(stop_geometry.get("noise_exposure") or "UNKNOWN").upper()
    research=archetype_research(archetype)
    h4_relation=_h4_relation(side,signal.get("regime"))
    strength=sum(bool(x) for x in (signal.get("checks") or {}).get(side,[]))

    try:
        cost=float(spread_to_risk)
    except Exception:
        cost=None

    blockers=[]
    cautions=[]
    score=0

    if side not in ("BUY","SELL"):
        blockers.append("no_direction")
    # Price-only proof can only test archetypes fully observable from bars.
    if archetype not in ("LIQUIDITY_REVERSAL","BREAKOUT_ACCEPTANCE"):
        blockers.append("price_only_archetype_not_qualified")
    if prior=="STABLE_NEGATIVE":
        blockers.append("legacy_reason_stable_negative")
    if research.get("status")=="RESEARCH_HOLD_NEGATIVE":
        blockers.append("v2_archetype_retrospective_negative")
    elif research.get("status")=="PROMISING_INSUFFICIENT_SAMPLE":
        cautions.append("v2_archetype_sample_insufficient")
    if stop_noise=="HIGH":
        blockers.append("stop_inside_market_noise")
    if cost is None:
        blockers.append("spread_to_risk_unknown")
    elif cost > 0.08:
        blockers.append("spread_to_risk_too_high")

    if not blockers:
        score += 2 if cost <= 0.05 else 1
        score += 3 if archetype=="LIQUIDITY_REVERSAL" else 2
        score += 2 if setup_score>=5 else (1 if setup_score>=3 else 0)
        if h4_relation=="ALIGNED":
            score+=1
        elif h4_relation=="COUNTER":
            cautions.append("h4_countertrend_tactical_only")
        if strength>=6:
            score+=1

    if blockers:
        state="REJECT"
    elif score>=7 and cost is not None and cost<=0.05:
        state="STRONG_PRICE_SHADOW_CANDIDATE"
    elif score>=5:
        state="PRICE_SHADOW_CANDIDATE"
    elif score>=3:
        state="WATCH"
    else:
        state="REJECT"

    if cost is None:
        cost_bucket="UNKNOWN"
    elif cost<=0.05:
        cost_bucket="LE_0_05R"
    elif cost<=0.08:
        cost_bucket="0_05_TO_0_08R"
    else:
        cost_bucket="GT_0_08R"

    return {
        "state":state,
        "score":int(score),
        "archetype":archetype,
        "setup_score":setup_score,
        "h4_relation":h4_relation,
        "strength":strength,
        "spread_to_risk":None if cost is None else round(cost,4),
        "cost_bucket":cost_bucket,
        "archetype_research":research,
        "blockers":sorted(set(blockers)),
        "cautions":sorted(set(cautions)),
        "authorizes_execution":False,
        "note":"price_only_sniper_v2_research_requires_multiwindow_proof",
    }


def assess(signal=None, setup=None, execution_quality=None, stop_geometry=None,
           uncertainty=None, evidence=None, macro=None, price_prior=None,
           readiness=None):
    signal=signal or {}
    setup=setup or {}
    execution_quality=execution_quality or {}
    stop_geometry=stop_geometry or {}
    uncertainty=uncertainty or {}
    evidence=evidence or {}
    macro=macro or {}
    price_prior=price_prior or {}
    readiness=readiness or {}

    side=str(signal.get("side") or "WAIT").upper()
    archetype=str(setup.get("primary") or "NO_CLEAR_ARCHETYPE").upper()
    setup_score=int(setup.get("primary_score") or 0)
    macro_phase=str(macro.get("phase") or "NORMAL").upper()
    exec_quality=str(execution_quality.get("quality") or "UNKNOWN").upper()
    stop_noise=str(stop_geometry.get("noise_exposure") or "UNKNOWN").upper()
    uncertainty_state=str(uncertainty.get("state") or "UNKNOWN").upper()
    evidence_state=str(evidence.get("state") or "UNKNOWN").upper()
    support=int(evidence.get("independent_support_count") or 0)
    conflict=int(evidence.get("independent_conflict_count") or 0)
    prior=str(price_prior.get("status") or "UNQUALIFIED_OR_UNKNOWN").upper()
    readiness_state=str(readiness.get("state") or "UNKNOWN").upper()
    research=archetype_research(archetype)
    h4_relation=_h4_relation(side,signal.get("regime"))
    cost=_cost_ratio(signal,execution_quality)

    blockers=[]
    cautions=[]
    score=0

    if side not in ("BUY","SELL"):
        blockers.append("no_direction")
    if archetype not in ALLOWED_ARCHETYPES:
        blockers.append("legacy_or_undifferentiated_archetype")
    if prior=="STABLE_NEGATIVE":
        blockers.append("legacy_reason_stable_negative")
    if research.get("status")=="RESEARCH_HOLD_NEGATIVE":
        blockers.append("v2_archetype_retrospective_negative")
    elif research.get("status")=="PROMISING_INSUFFICIENT_SAMPLE":
        cautions.append("v2_archetype_sample_insufficient")
    elif research.get("status")=="UNBACKFILLED":
        cautions.append("v2_archetype_no_price_backfill")
    if macro_phase in ("PRE_HIGH_EVENT","HIGH_EVENT_SHOCK_0_5M","PRE_MEDIUM_EVENT","MEDIUM_EVENT_SHOCK_0_5M"):
        blockers.append("event_first_move_untrusted")
    if exec_quality in ("BLOCKED_TERMINAL","STALE_TICK","EXTREME","UNKNOWN"):
        blockers.append("execution_quality_"+exec_quality.lower())
    if stop_noise=="HIGH":
        blockers.append("stop_inside_market_noise")
    if uncertainty_state=="HIGH_UNCERTAINTY":
        blockers.append("high_uncertainty")
    if evidence_state in ("BROAD_CONFLICT","MAJOR_CONTRADICTION"):
        blockers.append("independent_evidence_conflict")
    if readiness_state=="SHADOW_BLOCKED":
        blockers.append("analysis_readiness_blocked")
    if cost is None:
        blockers.append("spread_to_risk_unknown")
    elif cost > 0.08:
        blockers.append("spread_to_risk_too_high")

    if not blockers:
        # Cost mattered strongly in broker walk-forward, but these cutoffs stay
        # SHADOW until this new design earns fresh out-of-sample proof.
        if cost <= 0.05:
            score+=2
        else:
            score+=1
            cautions.append("cost_not_in_best_historical_bucket")

        if archetype=="LIQUIDITY_REVERSAL":
            score+=3
        elif archetype=="BREAKOUT_ACCEPTANCE":
            score+=2
        elif archetype=="EVENT_DIGESTION":
            score+=2
        elif archetype=="SQUEEZE_LIQUIDATION":
            score+=2

        if setup_score >= 5:
            score+=2
        elif setup_score >= 3:
            score+=1

        if evidence_state=="BROAD_SUPPORT":
            score+=2
        elif evidence_state=="LEAN_SUPPORT":
            score+=1
        elif support>=2 and conflict==0:
            score+=1

        if h4_relation=="ALIGNED":
            score+=1
        elif h4_relation=="COUNTER":
            cautions.append("h4_countertrend_tactical_only")

        strength=sum(bool(x) for x in (signal.get("checks") or {}).get(side,[]))
        if strength>=6:
            score+=1

        if uncertainty_state=="ELEVATED_UNCERTAINTY":
            score-=1
            cautions.append("elevated_uncertainty")

    if blockers:
        state="REJECT"
    elif score>=8 and cost is not None and cost<=0.05:
        state="STRONG_SHADOW_CANDIDATE"
    elif score>=6:
        state="SHADOW_CANDIDATE"
    elif score>=4:
        state="WATCH"
    else:
        state="REJECT"

    if cost is None:
        cost_bucket="UNKNOWN"
    elif cost<=0.05:
        cost_bucket="LE_0_05R"
    elif cost<=0.08:
        cost_bucket="0_05_TO_0_08R"
    else:
        cost_bucket="GT_0_08R"

    return {
        "state":state,
        "score":int(score),
        "archetype":archetype,
        "setup_score":setup_score,
        "h4_relation":h4_relation,
        "spread_to_risk":None if cost is None else round(float(cost),4),
        "cost_bucket":cost_bucket,
        "archetype_research":research,
        "evidence_state":evidence_state,
        "support_count":support,
        "conflict_count":conflict,
        "blockers":sorted(set(blockers)),
        "cautions":sorted(set(cautions)),
        "authorizes_execution":False,
        "legacy_sniper_replaced":False,
        "note":"new_tactical_shadow_design_requires_out_of_sample_proof",
    }
