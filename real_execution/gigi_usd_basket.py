"""Broker-native synthetic USD basket for Gigi shadow analysis.

This is deliberately NOT called DXY. It uses a DXY-style fixed FX basket from
the broker's own M15 candles, re-normalized to the pairs that are available.
It is context only: a strong dollar can be a gold headwind, but it is not a
standalone BUY/SELL rule because modern gold can decouple from FX.
"""
from __future__ import annotations

import math

# DXY-style currency weights, used only to build a transparent synthetic basket.
# Pairs quoted as XXXUSD are inverted with sign=-1 so positive means stronger USD.
PAIR_SPECS = {
    "EURUSD": (0.576, -1.0),
    "USDJPY": (0.136, +1.0),
    "GBPUSD": (0.119, -1.0),
    "USDCAD": (0.091, +1.0),
    "USDSEK": (0.042, +1.0),
    "USDCHF": (0.036, +1.0),
}
MIN_COVERAGE = 0.70
LOOKBACK_BARS = 4
HISTORY_WINDOWS = 36


def _closes(rows):
    out=[]
    for row in rows or []:
        try:
            value=float(row["close"])
            if value > 0:
                out.append(value)
        except Exception:
            continue
    return out


def _window_log_returns(values, window=LOOKBACK_BARS):
    if len(values) <= window:
        return []
    return [math.log(values[i] / values[i-window]) for i in range(window, len(values))]


def _zscore(current, history):
    vals=list(history or [])
    if len(vals) < 12:
        return 0.0
    mean=sum(vals)/len(vals)
    var=sum((x-mean)**2 for x in vals)/(len(vals)-1)
    sd=math.sqrt(max(0.0,var))
    return 0.0 if sd <= 1e-12 else (current-mean)/sd


def _corr(a,b):
    n=min(len(a),len(b))
    if n < 12:
        return 0.0
    a=a[-n:]; b=b[-n:]
    ma=sum(a)/n; mb=sum(b)/n
    va=sum((x-ma)**2 for x in a); vb=sum((x-mb)**2 for x in b)
    if va <= 1e-18 or vb <= 1e-18:
        return 0.0
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(va*vb)


def _gold_relationship(gold_rows, intermarket):
    gold_map={str(r.get('datetime') or ''):float(r['close']) for r in (gold_rows or []) if r.get('datetime') and r.get('close')}
    pair_maps={}
    for label,(_,orientation) in PAIR_SPECS.items():
        rows=intermarket.get(label) or []
        mp={str(r.get('datetime') or ''):float(r['close']) for r in rows if r.get('datetime') and r.get('close')}
        if mp:
            pair_maps[label]=(orientation,mp)
    if not gold_map or len(pair_maps) < 4:
        return {'state':'INSUFFICIENT','corr_short':0.0,'corr_long':0.0}
    common=set(gold_map)
    for _,mp in pair_maps.values():
        common &= set(mp)
    times=sorted(common)
    if len(times) < 50:
        return {'state':'INSUFFICIENT','corr_short':0.0,'corr_long':0.0}

    gold_ret=[]; usd_ret=[]
    for prev,cur in zip(times[:-1],times[1:]):
        gp=gold_map[prev]; gc=gold_map[cur]
        if gp<=0 or gc<=0: continue
        gr=math.log(gc/gp)
        wr=0.0; wsum=0.0
        for label,(orientation,mp) in pair_maps.items():
            a=mp[prev]; b=mp[cur]
            if a<=0 or b<=0: continue
            weight=PAIR_SPECS[label][0]
            wr += weight*orientation*math.log(b/a)
            wsum += weight
        if wsum > 0:
            gold_ret.append(gr); usd_ret.append(wr/wsum)
    if len(gold_ret) < 40:
        return {'state':'INSUFFICIENT','corr_short':0.0,'corr_long':0.0}
    short=_corr(gold_ret[-20:],usd_ret[-20:])
    long=_corr(gold_ret[-48:],usd_ret[-48:])
    if short*long < 0 and abs(short)>=0.25 and abs(long)>=0.25:
        state='RELATIONSHIP_FLIP'
    elif long <= -0.40 and short > long + 0.25:
        state='INVERSE_WEAKENING'
    elif long >= 0.25 and short < long - 0.25:
        state='POSITIVE_RELATION_WEAKENING'
    elif short <= -0.35:
        state='CLASSIC_INVERSE'
    elif short >= 0.25:
        state='DECOUPLED_POSITIVE'
    else:
        state='WEAK_OR_DECOUPLED'
    return {'state':state,'corr_short':round(short,3),'corr_long':round(long,3)}


def analyze(intermarket, gold_m15=None):
    intermarket=intermarket or {}
    components={}
    available_weight=0.0

    for label,(weight,orientation) in PAIR_SPECS.items():
        values=_closes(intermarket.get(label))
        windows=_window_log_returns(values)
        if len(windows) < 13:
            continue
        current=orientation*windows[-1]
        history=[orientation*x for x in windows[-(HISTORY_WINDOWS+1):-1]]
        z=_zscore(current,history)
        components[label]={
            "weight":weight,
            "oriented_log_return":current,
            "z":z,
            "direction":"USD_UP" if current>0 else ("USD_DOWN" if current<0 else "FLAT"),
        }
        available_weight += weight

    if available_weight < MIN_COVERAGE:
        return {
            "state":"INSUFFICIENT_COVERAGE",
            "gold_relationship":_gold_relationship(gold_m15,intermarket),
            "coverage":round(available_weight,3),
            "basket_z":0.0,
            "breadth":0.0,
            "components":components,
            "source":"BROKER_NATIVE_DXY_STYLE_SYNTHETIC",
            "official_dxy":False,
            "directional_signal":False,
        }

    weighted_z=0.0
    weighted_return=0.0
    for item in components.values():
        normalized=item["weight"]/available_weight
        weighted_z += normalized*float(item["z"])
        weighted_return += normalized*float(item["oriented_log_return"])

    sign=1 if weighted_z>0 else (-1 if weighted_z<0 else 0)
    agreeing=sum(
        item["weight"] for item in components.values()
        if sign and ((item["oriented_log_return"]>0) == (sign>0))
    )/available_weight if sign else 0.0

    if weighted_z >= 1.5 and agreeing >= 0.65:
        state="USD_STRONG_IMPULSE"
    elif weighted_z >= 0.8 and agreeing >= 0.55:
        state="USD_FIRM"
    elif weighted_z <= -1.5 and agreeing >= 0.65:
        state="USD_WEAK_IMPULSE"
    elif weighted_z <= -0.8 and agreeing >= 0.55:
        state="USD_SOFT"
    else:
        state="USD_MIXED"

    return {
        "state":state,
        "coverage":round(available_weight,3),
        "basket_z":round(weighted_z,3),
        "basket_4bar_bps":round(weighted_return*10000.0,2),
        "breadth":round(agreeing,3),
        "gold_relationship":_gold_relationship(gold_m15,intermarket),
        "components":{
            k:{
                "weight":v["weight"],
                "z":round(float(v["z"]),3),
                "direction":v["direction"],
            }
            for k,v in components.items()
        },
        "source":"BROKER_NATIVE_DXY_STYLE_SYNTHETIC",
        "official_dxy":False,
        "note":"synthetic_usd_context_not_ice_dxy_and_not_entry_signal",
        "directional_signal":False,
    }
