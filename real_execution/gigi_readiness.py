"""Unified Gigi shadow-readiness audit.

This module summarizes whether the ANALYSIS context is coherent enough to
review. It never opens, blocks, modifies or approves a REAL order.
"""
from __future__ import annotations


def audit(signal=None, quality=None, execution_quality=None, thesis=None,
          behavior=None, stop_geometry=None, exposure=None, context=None,
          target_geometry=None, price_prior=None, benchmark=None):
    signal=signal or {}
    quality=quality or {}
    execution_quality=execution_quality or {}
    thesis=thesis or {}
    behavior=behavior or {}
    stop_geometry=stop_geometry or {}
    exposure=exposure or {}
    context=context or {}
    target_geometry=target_geometry or {}
    price_prior=price_prior or {}
    benchmark=benchmark or {}

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
    target_state=str(target_geometry.get("state") or "UNKNOWN").upper()
    target_implied=str(target_geometry.get("implied_move_relation") or "UNKNOWN").upper()
    prior_state=str(price_prior.get("status") or "UNKNOWN").upper()
    benchmark_phase=str(benchmark.get("phase") or "UNKNOWN").upper()

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

    if target_state=="AMBITION_HIGH":
        warnings.append("target_ambition_high")
    elif target_state=="AMBITION_ELEVATED":
        warnings.append("target_ambition_elevated")
    if target_implied=="FAR_BEYOND_1D_PROXY":
        warnings.append("target_far_beyond_options_proxy")

    if prior_state=="STABLE_NEGATIVE":
        warnings.append("historical_price_prior_negative")
    elif prior_state=="UNQUALIFIED_OR_UNKNOWN":
        warnings.append("historical_price_prior_unqualified")

    if benchmark_phase=="AUCTION_OR_IMMEDIATE_POST":
        warnings.append("lbma_benchmark_window")
    elif benchmark_phase=="PRE_AUCTION":
        warnings.append("lbma_benchmark_pre_window")

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
        "target_geometry_state":target_state,
        "price_prior_state":prior_state,
        "benchmark_phase":benchmark_phase,
        "directional_signal":False,
        "execution_gate":False,
        "note":"analysis_readiness_only_not_order_approval",
    }
