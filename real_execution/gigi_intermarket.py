"""Dynamic intermarket context for Gigi REAL analysis.

Pure analysis only. Relationships are measured from recent broker-native bars;
nothing is hard-coded as "oil up => gold down" or vice versa.
"""
from __future__ import annotations

import math

FAMILY_MAP = {
    "WTI": "ENERGY",
    "BRENT": "ENERGY",
    "EURUSD": "USD_FX",
    "USDJPY": "USD_FX",
    "US500": "EQUITIES",
    "US100": "EQUITIES",
    "XAGUSD": "METALS",
}


def _family(name):
    return FAMILY_MAP.get(str(name or "").upper(), "OTHER:" + str(name or "").upper())



def _closes(rows):
    out=[]
    for r in rows or []:
        try:
            out.append(float(r["close"]))
        except Exception:
            continue
    return out


def _returns(values):
    out=[]
    for a,b in zip(values[:-1],values[1:]):
        if a:
            out.append((b-a)/abs(a))
    return out


def _corr(a,b,window=None):
    n=min(len(a),len(b))
    if window is not None:
        n=min(n,int(window))
    if n<8:
        return 0.0
    a=a[-n:]; b=b[-n:]
    ma=sum(a)/n; mb=sum(b)/n
    va=sum((x-ma)**2 for x in a)
    vb=sum((x-mb)**2 for x in b)
    if va<=1e-18 or vb<=1e-18:
        return 0.0
    cov=sum((x-ma)*(y-mb) for x,y in zip(a,b))
    return cov/math.sqrt(va*vb)


def _impulse(values, lookback=3):
    if len(values)<=lookback:
        return 0.0
    base=values[-1-lookback]
    return 0.0 if not base else (values[-1]-base)/abs(base)


def analyze(gold_m15, intermarket):
    gold=_closes(gold_m15)
    gold_ret=_returns(gold)
    details={}
    family_votes={}

    for name,rows in (intermarket or {}).items():
        vals=_closes(rows)
        rets=_returns(vals)
        corr_short=_corr(gold_ret,rets,24)
        corr_long=_corr(gold_ret,rets,64)
        impulse=_impulse(vals,3)

        if corr_short>=0.25 and corr_long>=0.25:
            stability="STABLE_POSITIVE"
        elif corr_short<=-0.25 and corr_long<=-0.25:
            stability="STABLE_NEGATIVE"
        elif abs(corr_short)>=0.25 and abs(corr_long)>=0.25 and corr_short*corr_long<0:
            stability="FLIPPING"
        elif abs(corr_short)>=0.35 and abs(corr_long)<0.20:
            stability="SHORT_ONLY"
        else:
            stability="WEAK"

        # Only stable relationships vote. A fresh short-window correlation
        # spike is recorded, but cannot masquerade as durable cross-market
        # confirmation.
        stable_corr=0.0
        if stability in ("STABLE_POSITIVE","STABLE_NEGATIVE"):
            stable_corr=(corr_short+corr_long)/2.0
        strength=min(1.0,abs(stable_corr))
        aligned_effect=stable_corr*impulse
        contribution=0.0
        if abs(stable_corr)>=0.30 and abs(impulse)>1e-8:
            contribution=strength if aligned_effect>0 else (-strength if aligned_effect<0 else 0.0)
            family_votes.setdefault(_family(name),[]).append(contribution)
        details[name]={
            "correlation": round(float(corr_short),3),
            "correlation_short": round(float(corr_short),3),
            "correlation_long": round(float(corr_long),3),
            "relationship_stability": stability,
            "impulse_3bar_pct": round(float(impulse*100.0),3),
            "relation": (
                "POSITIVE" if stable_corr>=0.30 else
                "NEGATIVE" if stable_corr<=-0.30 else
                "WEAK"
            ),
            "family": _family(name),
            "signed_contribution": round(float(contribution),3),
        }

    # Related markets are one evidence family. WTI+Brent or US500+US100 must
    # not count as two independent confirmations. Conflicting members within
    # the same family average toward zero.
    family_details={}
    bull=0.0
    bear=0.0
    for family,votes in family_votes.items():
        family_vote=max(-1.0,min(1.0,sum(votes)/len(votes))) if votes else 0.0
        family_details[family]={
            "vote": round(float(family_vote),3),
            "members": len(votes),
        }
        if family_vote>0:
            bull+=family_vote
        elif family_vote<0:
            bear+=abs(family_vote)

    net=bull-bear
    if net>=0.75:
        bias="BULLISH_GOLD"
    elif net<=-0.75:
        bias="BEARISH_GOLD"
    else:
        bias="NEUTRAL"

    states=[str(v.get("relationship_stability") or "WEAK") for v in details.values()]
    if any(s=="FLIPPING" for s in states):
        relationship_state="FLIPPING_PRESENT"
    elif any(s.startswith("STABLE_") for s in states):
        relationship_state="STABLE_PRESENT"
    elif any(s=="SHORT_ONLY" for s in states):
        relationship_state="SHORT_ONLY_PRESENT"
    else:
        relationship_state="WEAK"

    return {
        "bias": bias,
        "bull_evidence": round(bull,3),
        "bear_evidence": round(bear,3),
        "net_family_evidence": round(net,3),
        "relationship_state": relationship_state,
        "family_details": family_details,
        "details": details,
        "method": "dual_window_correlation_family_deduplicated",
    }
