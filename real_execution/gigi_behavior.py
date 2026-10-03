"""Decision-hygiene guard for Gigi shadow analysis.

Flags common trading-process mistakes without blocking trades or changing the
direction score. The purpose is to catch confirmation bias, news chasing and
overtrading/concentration when a technical setup looks persuasive.
"""
from __future__ import annotations


def assess(signal=None, context=None, thesis=None, exposure=None, stop_geometry=None):
    signal=signal or {}
    context=context or {}
    thesis=thesis or {}
    exposure=exposure or {}
    stop_geometry=stop_geometry or {}

    side=str(signal.get("side") or "WAIT").upper()
    checks=(signal.get("checks") or {}).get(side, []) if side in ("BUY","SELL") else []
    technical_strength=sum(bool(x) for x in checks)
    alignment=str(context.get("alignment") or "MIXED").upper()
    context_reasons=set(context.get("reasons") or [])
    thesis_state=str(thesis.get("state") or "UNPROVEN").upper()
    conflict_count=int(thesis.get("conflict_count") or 0)
    stacking=str(exposure.get("stacking_state") or "CLEAR").upper()
    noise=str(stop_geometry.get("noise_exposure") or "UNKNOWN").upper()

    flags=[]

    if technical_strength >= 6 and (thesis_state=="FRAGILE" or conflict_count>=2):
        flags.append("confirmation_bias_risk")

    if technical_strength >= 6 and alignment in ("CONFLICT","STRONG_CONFLICT"):
        flags.append("technical_score_context_conflict")

    if "first_spike_untrusted" in context_reasons:
        flags.append("news_first_spike_chase_risk")

    if stacking in ("CONCENTRATED","HIGH_CONCENTRATION") and alignment not in ("STRONG_SUPPORT",):
        flags.append("overtrading_concentration_risk")

    if noise=="HIGH":
        flags.append("stop_inside_market_noise_risk")

    if thesis_state=="CLEAN" and not flags:
        hygiene="CLEAN"
    elif len(flags)>=2:
        hygiene="HIGH_ATTENTION"
    elif flags:
        hygiene="ATTENTION"
    else:
        hygiene="NORMAL"

    return {
        "state":hygiene,
        "flags":sorted(set(flags)),
        "technical_strength":technical_strength,
        "context_alignment":alignment,
        "thesis_state":thesis_state,
        "directional_signal":False,
        "execution_gate":False,
        "note":"behavioral_guard_shadow_only",
    }
