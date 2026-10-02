from __future__ import annotations
import math

def ema(v,n):
    a=2/(n+1); o=[float(v[0])]
    for x in v[1:]: o.append(a*float(x)+(1-a)*o[-1])
    return o

def _shape(r):
    o,h,l,c=r["open"],r["high"],r["low"],r["close"]; body=abs(c-o); rng=max(h-l,1e-9)
    return body,rng,h-max(o,c),min(o,c)-l

def patterns(rows):
    bull=[]; bear=[]; neutral=[]
    if len(rows)<6:return bull,bear,neutral
    a,b,c=rows[-3:]; body,rng,up,lo=_shape(c); bb,br,_,_=_shape(b)
    prior_down=rows[-4]["close"]>b["close"]; prior_up=rows[-4]["close"]<b["close"]
    if body/rng<=.10: neutral.append("doji")
    if body/rng<=.30 and up/rng>=.25 and lo/rng>=.25: neutral.append("spinning_top")
    if body/rng>=.85:(bull if c["close"]>c["open"] else bear).append("marubozu")
    if lo>=2*max(body,.01) and up<=max(body,.01):(bull if prior_down else bear).append("hammer" if prior_down else "hanging_man")
    if up>=2*max(body,.01) and lo<=max(body,.01):(bull if prior_down else bear).append("inverted_hammer" if prior_down else "shooting_star")
    if b["close"]<b["open"] and c["close"]>c["open"] and c["open"]<=b["close"] and c["close"]>=b["open"]:bull.append("bullish_engulfing")
    if b["close"]>b["open"] and c["close"]<c["open"] and c["open"]>=b["close"] and c["close"]<=b["open"]:bear.append("bearish_engulfing")
    mid=(b["open"]+b["close"])/2
    if b["close"]<b["open"] and c["close"]>c["open"] and mid<c["close"]<b["open"]:bull.append("piercing_line")
    if b["close"]>b["open"] and c["close"]<c["open"] and b["open"]<c["close"]<mid:bear.append("dark_cloud")
    tol=max(.05,.04*(br+rng))
    if abs(c["low"]-b["low"])<=tol and c["close"]>c["open"]:bull.append("tweezer_bottom")
    if abs(c["high"]-b["high"])<=tol and c["close"]<c["open"]:bear.append("tweezer_top")
    ab,ar,_,_=_shape(a)
    if a["close"]<a["open"] and bb/br<=.35 and c["close"]>c["open"] and c["close"]>(a["open"]+a["close"])/2:bull.append("morning_star")
    if a["close"]>a["open"] and bb/br<=.35 and c["close"]<c["open"] and c["close"]<(a["open"]+a["close"])/2:bear.append("evening_star")
    x,y,z=rows[-3:]
    if all(q["close"]>q["open"] for q in (x,y,z)) and x["close"]<y["close"]<z["close"]:bull.append("three_white_soldiers")
    if all(q["close"]<q["open"] for q in (x,y,z)) and x["close"]>y["close"]>z["close"]:bear.append("three_black_crows")
    f0,f1,f2,f3,f4=rows[-5:]
    if f0["close"]>f0["open"] and f4["close"]>f4["open"] and f4["close"]>f0["high"] and all(q["close"]<q["open"] and f0["low"]<=q["low"]<=q["high"]<=f0["high"] for q in (f1,f2,f3)):bull.append("rising_three_methods")
    if f0["close"]<f0["open"] and f4["close"]<f4["open"] and f4["close"]<f0["low"] and all(q["close"]>q["open"] and f0["low"]<=q["low"]<=q["high"]<=f0["high"] for q in (f1,f2,f3)):bear.append("falling_three_methods")
    return bull,bear,neutral

def adx_di(rows,n=14):
    if len(rows)<n+2:return 0.,0.,0.
    tr=[];p=[];m=[]
    for i in range(1,len(rows)):
        up=rows[i]["high"]-rows[i-1]["high"];dn=rows[i-1]["low"]-rows[i]["low"];pc=rows[i-1]["close"]
        tr.append(max(rows[i]["high"]-rows[i]["low"],abs(rows[i]["high"]-pc),abs(rows[i]["low"]-pc)))
        p.append(up if up>dn and up>0 else 0);m.append(dn if dn>up and dn>0 else 0)
    atr=sum(tr[-n:])
    if atr<=0:return 0.,0.,0.
    pp=100*sum(p[-n:])/atr;mm=100*sum(m[-n:])/atr
    return 100*abs(pp-mm)/max(pp+mm,1e-9),pp,mm

def adx(rows,n=14):
    return adx_di(rows,n)[0]

def analyze(rows):
    closes=[r["close"] for r in rows]; e9=ema(closes,9);e21=ema(closes,21);e50=ema(closes,50)
    e200=ema(closes,200) if len(closes)>=200 else []
    e12=ema(closes,12);e26=ema(closes,26); line=[x-y for x,y in zip(e12,e26)]; sig=ema(line,9); hist=line[-1]-sig[-1]
    xs=closes[-20:];mid=sum(xs)/len(xs);sd=math.sqrt(sum((x-mid)**2 for x in xs)/len(xs));upper=mid+2*sd;lower=mid-2*sd
    volrows=[r for r in rows[-50:] if float(r.get("tick_volume") or 0)>0]; den=sum(float(r["tick_volume"]) for r in volrows)
    vw=sum(((r["high"]+r["low"]+r["close"])/3)*float(r["tick_volume"]) for r in volrows)/den if den else None
    bull,bear,neutral=patterns(rows); close=closes[-1]
    ax,plus_di,minus_di=adx_di(rows)
    recent_vol=[float(r.get("tick_volume") or 0) for r in rows[-21:]]
    valid_vol=[v for v in recent_vol[:-1] if v>0]
    volume_ratio=(recent_vol[-1]/(sum(valid_vol)/len(valid_vol))) if recent_vol[-1]>0 and valid_vol else None
    bull += ["ema9_21"] if e9[-1]>e21[-1] else []
    bear += ["ema9_21"] if e9[-1]<e21[-1] else []
    bull += ["above_ema50"] if close>e50[-1] else []; bear += ["below_ema50"] if close<e50[-1] else []
    if e200: (bull if close>e200[-1] else bear).append("ema200")
    (bull if hist>0 else bear).append("macd")
    if vw is not None:(bull if close>vw else bear).append("vwap")
    if close<=lower:bull.append("bollinger_lower")
    elif close>=upper:bear.append("bollinger_upper")
    return {"bull_score":len(bull),"bear_score":len(bear),"bull":bull,"bear":bear,"neutral":neutral,
            "ema9":e9[-1],"ema21":e21[-1],"ema50":e50[-1],"ema200":e200[-1] if e200 else None,
            "macd_hist":hist,"boll_upper":upper,"boll_lower":lower,"vwap":vw,"adx":ax,
            "plus_di":plus_di,"minus_di":minus_di,"volume_ratio":volume_ratio}
