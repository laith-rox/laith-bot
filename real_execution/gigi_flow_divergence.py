"""Slow-flow divergence context for Gigi shadow analysis.

Gold can fall while ETF demand rises if futures positioning is liquidating, or
rise while ETF flows are weak if short covering dominates. This layer labels
that disagreement instead of pretending all "flow" inputs are one signal.
Research-only: never an entry trigger or execution gate.
"""
from __future__ import annotations


def analyze(etf=None, positioning=None, regime=None):
    etf=etf or {}
    positioning=positioning or {}
    regime=regime or {}

    etf_regime=str(etf.get("regime") or "UNKNOWN").upper()
    pos_regime=str(positioning.get("regime") or "UNKNOWN").upper()
    h4=str(regime.get("h4_bias") or "NEUTRAL").upper()

    etf_in=etf_regime in ("BROAD_INFLOW","MIXED_INFLOW")
    etf_out=etf_regime in ("BROAD_OUTFLOW","MIXED_OUTFLOW")
    futures_bull=pos_regime in ("LONG_BIASED_ADDING","SHORT_BIASED_COVERING")
    futures_bear=pos_regime in ("SHORT_BIASED_ADDING","LONG_BIASED_DELEVERAGING")

    if etf_in and futures_bear:
        state="ETF_BUYING_VS_FUTURES_LIQUIDATION"
        divergence=True
    elif etf_out and futures_bull:
        state="ETF_SELLING_VS_FUTURES_COVERING"
        divergence=True
    elif etf_in and futures_bull:
        state="FLOW_CONFIRMATION_BULLISH"
        divergence=False
    elif etf_out and futures_bear:
        state="FLOW_CONFIRMATION_BEARISH"
        divergence=False
    elif etf_regime=="UNKNOWN" or pos_regime=="UNKNOWN":
        state="UNKNOWN"
        divergence=False
    else:
        state="MIXED_FLOW"
        divergence=False

    if state=="ETF_BUYING_VS_FUTURES_LIQUIDATION":
        if h4=="DOWN":
            price_alignment="PRICE_ALIGNS_FUTURES_LIQUIDATION"
        elif h4=="UP":
            price_alignment="PRICE_RESISTS_FUTURES_LIQUIDATION"
        else:
            price_alignment="PRICE_UNRESOLVED"
    elif state=="ETF_SELLING_VS_FUTURES_COVERING":
        if h4=="UP":
            price_alignment="PRICE_ALIGNS_FUTURES_COVERING"
        elif h4=="DOWN":
            price_alignment="PRICE_RESISTS_FUTURES_COVERING"
        else:
            price_alignment="PRICE_UNRESOLVED"
    elif state=="FLOW_CONFIRMATION_BULLISH":
        price_alignment="PRICE_CONFIRMS" if h4=="UP" else ("PRICE_DIVERGES" if h4=="DOWN" else "PRICE_UNRESOLVED")
    elif state=="FLOW_CONFIRMATION_BEARISH":
        price_alignment="PRICE_CONFIRMS" if h4=="DOWN" else ("PRICE_DIVERGES" if h4=="UP" else "PRICE_UNRESOLVED")
    else:
        price_alignment="UNKNOWN"

    return {
        "state":state,
        "divergence":bool(divergence),
        "price_alignment":price_alignment,
        "etf_regime":etf_regime,
        "positioning_regime":pos_regime,
        "h4_bias":h4,
        "directional_signal":False,
        "execution_gate":False,
        "note":"slow_flow_divergence_context_not_entry_signal",
    }
