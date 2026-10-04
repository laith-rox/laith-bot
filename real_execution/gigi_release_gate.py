"""Research promotion gate for Gigi candidate analysis.

This is deliberately stricter than "more tools = better". A mode is not ready
to be trusted merely because unit tests pass or because many context layers
agree. Historical market proof must survive independent chronological windows.

Research/shadow only: never authorizes, blocks, sizes or sends a REAL order.
"""
from __future__ import annotations


def assess(market_proof=None):
    proof=market_proof or {}
    mode_status=str(proof.get("mode_status") or "UNKNOWN").upper()
    reason_status=str(proof.get("reason_status") or "UNQUALIFIED_OR_UNKNOWN").upper()
    n=int(proof.get("mode_total_n") or 0)
    mean=float(proof.get("mode_weighted_mean_r") or 0.0)

    reasons=[]
    if mode_status=="STABLE_NEGATIVE":
        state="RESEARCH_HOLD"
        reasons.append("mode_negative_across_all_walkforward_windows")
    elif reason_status=="STABLE_NEGATIVE":
        state="RESEARCH_HOLD"
        reasons.append("setup_reason_stable_negative")
    elif mode_status=="PROMISING_UNSTABLE":
        state="SHADOW_ONLY"
        reasons.append("positive_average_but_not_stable_across_windows")
    elif mode_status=="STABLE_POSITIVE":
        if reason_status=="STABLE_POSITIVE":
            state="EVIDENCE_CANDIDATE"
            reasons.append("mode_and_reason_stable_positive")
        else:
            state="SHADOW_ONLY"
            reasons.append("mode_positive_but_setup_reason_unqualified")
    elif mode_status in ("NEGATIVE_UNSTABLE","UNKNOWN"):
        state="RESEARCH_HOLD"
        reasons.append("market_proof_not_positive")
    else:
        state="SHADOW_ONLY"
        reasons.append("market_proof_incomplete")

    if n < 100:
        if state=="EVIDENCE_CANDIDATE":
            state="SHADOW_ONLY"
        reasons.append("sample_too_small_for_promotion")

    return {
        "state":state,
        "mode_status":mode_status,
        "reason_status":reason_status,
        "mode_total_n":n,
        "mode_weighted_mean_r":round(mean,4),
        "reasons":reasons,
        "authorizes_execution":False,
        "execution_gate":False,
        "note":"research_promotion_gate_only_not_real_order_authorization",
    }
