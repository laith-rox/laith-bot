"""Uncertainty / abstention context for Gigi shadow analysis.

A smart analyst must know when evidence is conflicted or incomplete. This layer
does not block execution and does not place orders. It records when confidence
should be reduced so later calibration can test whether abstention was useful.
"""
from __future__ import annotations


def assess(signal=None, context=None, evidence=None, data_quality=None, macro=None, regime=None):
    signal=signal or {}
    context=context or {}
    evidence=evidence or {}
    data_quality=data_quality or {}
    macro=macro or {}
    regime=regime or {}

    score=0
    reasons=[]

    quality=str(data_quality.get("quality") or "LOW").upper()
    if quality=="LOW":
        score+=3; reasons.append("low_external_data_quality")
    elif quality=="MEDIUM":
        score+=1; reasons.append("medium_external_data_quality")

    ev_state=str(evidence.get("state") or "UNKNOWN").upper()
    support=int(evidence.get("support_count") or 0)
    conflict=int(evidence.get("conflict_count") or 0)
    if ev_state in ("CONTRADICTED","MIXED","CONFLICTED"):
        score+=3; reasons.append("evidence_conflicted")
    elif support > 0 and conflict > 0:
        score+=2; reasons.append("two_sided_evidence")

    regime_name=str(regime.get("name") or "UNKNOWN").upper()
    if regime_name in ("TRANSITION","VOLATILE_TRANSITION"):
        score+=2; reasons.append("transition_regime")
    elif regime_name=="UNKNOWN":
        score+=2; reasons.append("regime_unknown")

    macro_regime=str(macro.get("regime") or "UNKNOWN").upper()
    macro_phase=str(macro.get("phase") or "NORMAL").upper()
    if macro_regime=="UNKNOWN":
        score+=2; reasons.append("macro_unknown")
    if macro_phase in ("PRE_HIGH_EVENT","HIGH_EVENT_SHOCK_0_5M"):
        score+=3; reasons.append("event_direction_not_settled")
    elif macro_phase=="HIGH_EVENT_DIGESTION_5_15M":
        score+=1; reasons.append("event_price_discovery")

    side=str(signal.get("side") or "WAIT").upper()
    if side not in ("BUY","SELL"):
        score+=1; reasons.append("no_directional_setup")

    alignment=str(context.get("alignment") or "MIXED").upper()
    if alignment=="MIXED":
        score+=1; reasons.append("context_mixed")
    elif alignment in ("CONFLICT","STRONG_CONFLICT"):
        score+=2; reasons.append("context_conflicts_setup")

    if score >= 8:
        state="HIGH_UNCERTAINTY"
        posture="ABSTAIN_SHADOW"
    elif score >= 4:
        state="ELEVATED_UNCERTAINTY"
        posture="REDUCE_CONFIDENCE"
    else:
        state="NORMAL_UNCERTAINTY"
        posture="NORMAL_ANALYSIS"

    return {
        "state":state,
        "posture":posture,
        "uncertainty_score":int(score),
        "reasons":reasons,
        "execution_gate":False,
        "note":"shadow_uncertainty_not_execution_control",
    }
