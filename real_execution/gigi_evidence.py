"""Independent evidence-family audit for Gigi shadow analysis.

Correlated inputs are collapsed into a few evidence families. This module does
not place orders and does not emit a standalone BUY/SELL decision.
"""
from __future__ import annotations


def _vote(value):
    try:
        value=int(value)
    except Exception:
        return 0
    return 1 if value>0 else (-1 if value<0 else 0)


def _price_vote(side, regime, liquidity, session_profile):
    side=str(side or "WAIT").upper()
    h4=str((regime or {}).get("h4_bias") or "NEUTRAL").upper()
    pressure=str((liquidity or {}).get("pressure") or "NEUTRAL").upper()
    vwap=str((session_profile or {}).get("vwap_relation") or "UNKNOWN").upper()
    raw=0
    if side=="BUY":
        raw += 1 if h4=="UP" else (-1 if h4=="DOWN" else 0)
        raw += 1 if pressure=="BULLISH" else (-1 if pressure=="BEARISH" else 0)
        raw += 1 if vwap=="ABOVE_ACCEPTANCE" else (-1 if vwap=="BELOW_ACCEPTANCE" else 0)
    elif side=="SELL":
        raw += 1 if h4=="DOWN" else (-1 if h4=="UP" else 0)
        raw += 1 if pressure=="BEARISH" else (-1 if pressure=="BULLISH" else 0)
        raw += 1 if vwap=="BELOW_ACCEPTANCE" else (-1 if vwap=="ABOVE_ACCEPTANCE" else 0)
    return _vote(raw)


def _macro_vote(side, yields, usd_basket, macro_surprise):
    side=str(side or "WAIT").upper()
    real_yield=str((yields or {}).get("real_yield_regime") or "UNKNOWN").upper()
    usd=str((usd_basket or {}).get("state") or "UNKNOWN").upper()
    surprise=str((macro_surprise or {}).get("bundle_surprise") or "UNKNOWN").upper()
    gold_macro=0
    gold_macro += -1 if real_yield=="RISING_REAL_YIELD" else (1 if real_yield=="FALLING_REAL_YIELD" else 0)
    gold_macro += -1 if usd in ("USD_STRONG_IMPULSE","USD_FIRM") else (1 if usd in ("USD_WEAK_IMPULSE","USD_SOFT") else 0)
    gold_macro += -1 if surprise=="USD_POSITIVE" else (1 if surprise=="USD_NEGATIVE" else 0)
    return _vote(gold_macro if side=="BUY" else (-gold_macro if side=="SELL" else 0))


def _flow_vote(side, positioning, etf, crowding):
    side=str(side or "WAIT").upper()
    pos=str((positioning or {}).get("regime") or "UNKNOWN").upper()
    etf_state=str((etf or {}).get("regime") or "UNKNOWN").upper()
    crowd=str((crowding or {}).get("dominant_risk") or "BALANCED").upper()
    gold_flow=0
    if pos in ("LONG_BIASED_ADDING","SHORT_BIASED_COVERING"):
        gold_flow+=1
    elif pos in ("SHORT_BIASED_ADDING","LONG_BIASED_DELEVERAGING"):
        gold_flow-=1
    if etf_state=="BROAD_INFLOW":
        gold_flow+=1
    elif etf_state=="BROAD_OUTFLOW":
        gold_flow-=1
    if crowd in ("HIGH_SHORT_SQUEEZE","WATCH_SHORT_SQUEEZE","SHORT_SQUEEZE_BIAS"):
        gold_flow+=1
    elif crowd in ("HIGH_LONG_LIQUIDATION","WATCH_LONG_LIQUIDATION","LONG_LIQUIDATION_BIAS"):
        gold_flow-=1
    return _vote(gold_flow if side=="BUY" else (-gold_flow if side=="SELL" else 0))


def _options_vote(side, options, volatility):
    """Directional vote from *skew only*; raw OI is deliberately unsigned.

    Call-heavy or put-heavy open interest does not reveal whether customers are
    net long or short those options, nor dealer hedge direction. Treating raw OI
    as bullish/bearish would manufacture independent evidence. Skew is retained
    as a weak preference proxy; gamma/OI/term structure remain context only.
    """
    side=str(side or "WAIT").upper()
    skew=str((options or {}).get("skew") or "UNKNOWN").upper()
    oi=str((options or {}).get("oi_state") or "UNKNOWN").upper()
    vol_state=str((volatility or {}).get("state") or "UNKNOWN").upper()
    gold_opt=0
    if skew=="UPSIDE_CALL_BID":
        gold_opt=1
    elif skew=="DOWNSIDE_HEDGE_BID":
        gold_opt=-1
    # Intentionally do not vote on CALL_HEAVY / PUT_HEAVY OI.
    if vol_state=="UNKNOWN" and skew=="UNKNOWN" and oi=="UNKNOWN":
        return 0
    return _vote(gold_opt if side=="BUY" else (-gold_opt if side=="SELL" else 0))


def _cross_market_vote(side, intermarket, local_premium):
    side=str(side or "WAIT").upper()
    bias=str((intermarket or {}).get("bias") or "NEUTRAL").upper()
    china=str(((local_premium or {}).get("china") or {}).get("state") or "UNKNOWN").upper()
    india=str(((local_premium or {}).get("india") or {}).get("state") or "UNKNOWN").upper()
    gold_cross=0
    gold_cross += 1 if bias=="BULLISH_GOLD" else (-1 if bias=="BEARISH_GOLD" else 0)
    for state in (china,india):
        if state in ("PREMIUM","STRONG_PREMIUM"):
            gold_cross+=1
        elif state in ("DISCOUNT","STRONG_DISCOUNT"):
            gold_cross-=1
    return _vote(gold_cross if side=="BUY" else (-gold_cross if side=="SELL" else 0))


def audit(side, regime=None, liquidity=None, session_profile=None, yields=None,
          usd_basket=None, macro_surprise=None, positioning=None, etf=None,
          crowding=None, options=None, volatility=None, intermarket=None,
          local_premium=None):
    families={
        "PRICE_STRUCTURE":_price_vote(side,regime,liquidity,session_profile),
        "MACRO_POLICY":_macro_vote(side,yields,usd_basket,macro_surprise),
        "FLOWS_POSITIONING":_flow_vote(side,positioning,etf,crowding),
        "OPTIONS_VOLATILITY":_options_vote(side,options,volatility),
        "CROSS_MARKET_PHYSICAL":_cross_market_vote(side,intermarket,local_premium),
    }
    support=sum(v>0 for v in families.values())
    conflict=sum(v<0 for v in families.values())
    neutral=sum(v==0 for v in families.values())
    active=support+conflict

    if active < 2:
        state="THIN_EVIDENCE"
    elif support>=3 and conflict==0:
        state="BROAD_SUPPORT"
    elif conflict>=3 and support==0:
        state="BROAD_CONFLICT"
    elif support>=2 and conflict>=2:
        state="MAJOR_CONTRADICTION"
    elif support>conflict:
        state="LEAN_SUPPORT"
    elif conflict>support:
        state="LEAN_CONFLICT"
    else:
        state="MIXED"

    return {
        "state":state,
        "families":families,
        "independent_support_count":support,
        "independent_conflict_count":conflict,
        "neutral_family_count":neutral,
        "active_family_count":active,
        "correlated_inputs_collapsed":True,
        "note":"evidence_family_audit_not_probability_or_entry_signal",
    }
