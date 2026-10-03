"""Dynamic intermarket context for Gigi REAL analysis.

Pure analysis only. Relationships are measured from recent broker-native bars;
nothing is hard-coded as "oil up => gold down" or vice versa.
"""
from __future__ import annotations

import math


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


def _corr(a,b):
    n=min(len(a),len(b))
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
    bull=0.0
    bear=0.0

    for name,rows in (intermarket or {}).items():
        vals=_closes(rows)
        rets=_returns(vals)
        corr=_corr(gold_ret,rets)
        impulse=_impulse(vals,3)
        strength=min(1.0,abs(corr))
        aligned_effect=corr*impulse
        if abs(corr)>=0.30 and abs(impulse)>1e-8:
            if aligned_effect>0:
                bull += strength
            elif aligned_effect<0:
                bear += strength
        details[name]={
            "correlation": round(float(corr),3),
            "impulse_3bar_pct": round(float(impulse*100.0),3),
            "relation": (
                "POSITIVE" if corr>=0.30 else
                "NEGATIVE" if corr<=-0.30 else
                "WEAK"
            ),
        }

    net=bull-bear
    if net>=0.75:
        bias="BULLISH_GOLD"
    elif net<=-0.75:
        bias="BEARISH_GOLD"
    else:
        bias="NEUTRAL"

    return {
        "bias": bias,
        "bull_evidence": round(bull,3),
        "bear_evidence": round(bear,3),
        "details": details,
        "method": "rolling_correlation_dynamic",
    }
