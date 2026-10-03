"""Unified Gigi shadow-readiness audit.

This module summarizes whether the ANALYSIS context is coherent enough to
review. It never opens, blocks, modifies or approves a REAL order.
"""
from __future__ import annotations


def audit(signal=None, quality=None, execution_quality=None, thesis=None,
          behavior=None, stop_geometry=None, exposure=None, context=None):
    signal=signal or {}
    quality=quality or {}
    execution_quality=execution_quality or {}
    thesis=thesis or {}
    behavior=behavior or {}
    stop_geometry=stop_geometry or {}
    exposure=exposure or {}
    context=context or {}

    side=str(signal.get("side") or "WAIT").upper()
    blockers=[]
    warnings=[]

    data_quality=str(quality.get("quality") or "UNKNOWN").upper()
    exec_quality=str(execution_quality.get("quality") or "UNKNOWN").upper()
    thesis_state=str(thesis.get("state") or "UNPROVEN").upper()
    behavior_state=str(behavior.get("state") or "UNKNOWN").upper()
    stop_noise=str(stop_geometry.get("noise_exposure") or "UNKNOWN").upper()
    stacking=str(exposure.get("stacking_state") or "CLEAR").upper()
    alignment=str(context.get("alignment") or "MIXED").upper()

    if side not in ("BUY","SELL"):
        blockers.append("no_directional_setup")

    if exec_quality in ("BLOCKED_TERMINAL","STALE_TICK","EXTREME"):
        blockers.append("execution_quality_"+exec_quality.lower())
    elif exec_quality in ("WIDE","UNKNOWN"):
        warnings.append("execution_quality_"+exec_quality.lower())

    if data_quality=="LOW":
        warnings.append("external_data_quality_low")
    elif data_quality=="UNKNOWN":
        warnings.append("external_data_quality_unknown")

    if thesis_state=="FRAGILE":
        warnings.append("thesis_fragile")
    elif thesis_state=="UNPROVEN":
        warnings.append("thesis_unproven")

    if behavior_state=="HIGH_ATTENTION":
        warnings.append("behavior_high_attention")
    elif behavior_state=="ATTENTION":
        warnings.append("behavior_attention")

    if stop_noise=="HIGH":
        warnings.append("stop_inside_market_noise")
    elif stop_noise=="UNKNOWN":
        warnings.append("stop_geometry_unknown")

    if stacking=="HIGH_CONCENTRATION":
        warnings.append("exposure_high_concentration")
    elif stacking=="CONCENTRATED":
        warnings.append("exposure_concentrated")

    if alignment in ("CONFLICT","STRONG_CONFLICT"):
        warnings.append("context_conflicts_setup")

    if blockers:
        state="SHADOW_BLOCKED"
    elif len(warnings)>=3:
        state="SHADOW_CAUTION"
    elif warnings:
        state="SHADOW_REVIEW"
    else:
        state="SHADOW_CLEAN"

    return {
        "state":state,
        "blockers":sorted(set(blockers)),
        "warnings":sorted(set(warnings)),
        "data_quality":data_quality,
        "execution_quality":exec_quality,
        "thesis_state":thesis_state,
        "behavior_state":behavior_state,
        "alignment":alignment,
        "directional_signal":False,
        "execution_gate":False,
        "note":"analysis_readiness_only_not_order_approval",
    }
