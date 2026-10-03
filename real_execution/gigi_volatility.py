"""Volatility and options-proxy context for Gigi shadow analysis.

Combines broker-native realised-volatility behaviour with Cboe GVZ, which is an
options-implied volatility index for GLD. GVZ is a proxy, not CME gold-futures
options and not a directional signal.
"""
from __future__ import annotations

import csv
import io
import math
import time
import urllib.request

try:
    import requests
except Exception:
    requests = None

GVZ_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv"
CACHE_SECONDS = 30 * 60
_cache = {"fetched_at": 0.0, "value": None}


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


def _log_returns(values):
    out=[]
    for a,b in zip(values[:-1], values[1:]):
        if a > 0 and b > 0:
            out.append(math.log(b/a))
    return out


def _stdev(values):
    n=len(values)
    if n < 2:
        return 0.0
    mean=sum(values)/n
    var=sum((x-mean)**2 for x in values)/(n-1)
    return math.sqrt(max(0.0,var))


def realised_context(m15):
    closes=_closes(m15)
    returns=_log_returns(closes)
    if len(returns) < 30:
        return {
            "rv_state":"UNKNOWN",
            "rv_ratio":0.0,
            "short_sigma":0.0,
            "baseline_sigma":0.0,
        }

    short=returns[-16:]   # about 4 hours on M15
    baseline=returns[-64:] if len(returns) >= 64 else returns
    short_sigma=_stdev(short)
    base_sigma=_stdev(baseline)
    ratio=(short_sigma/base_sigma) if base_sigma > 1e-12 else 0.0

    if ratio >= 1.60:
        state="EXPLOSIVE"
    elif ratio >= 1.25:
        state="EXPANDING"
    elif ratio <= 0.65:
        state="COMPRESSED"
    else:
        state="NORMAL"

    return {
        "rv_state":state,
        "rv_ratio":round(float(ratio),3),
        "short_sigma":round(float(short_sigma),8),
        "baseline_sigma":round(float(base_sigma),8),
    }


def parse_gvz_csv(raw):
    rows=[]
    for row in csv.DictReader(io.StringIO(str(raw))):
        try:
            rows.append((str(row["DATE"]), float(row["GVZ"])))
        except Exception:
            continue
    if len(rows) < 30:
        raise ValueError("gvz_history_too_short")

    date,value=rows[-1]
    history=[v for _,v in rows[-252:]]
    ranked=sum(1 for v in history if v <= value)
    percentile=ranked/len(history)
    change_5=value-rows[-6][1] if len(rows) >= 6 else 0.0

    if percentile >= 0.85:
        regime="ELEVATED"
    elif percentile <= 0.20:
        regime="LOW"
    else:
        regime="NORMAL"

    return {
        "gvz_date":date,
        "gvz":round(value,3),
        "gvz_change_5d":round(change_5,3),
        "gvz_percentile_1y":round(percentile,3),
        "gvz_regime":regime,
        "source":"CBOE_GVZ_GLD_OPTIONS_PROXY",
        "proxy_note":"GLD_options_implied_volatility_not_CME_gold_futures",
    }


def fetch_gvz(now=None, opener=None):
    now=time.time() if now is None else float(now)
    if _cache["value"] is not None and now-float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])
    headers={"User-Agent":"Laith-Gigi-GVZ/1.0","Accept":"text/csv"}
    try:
        if opener is not None:
            req=urllib.request.Request(GVZ_URL,headers=headers)
            with opener(req,timeout=8) as res:
                raw=res.read().decode("utf-8",errors="replace")
        elif requests is not None:
            res=requests.get(GVZ_URL,timeout=8,headers=headers)
            res.raise_for_status()
            raw=res.text
        else:
            req=urllib.request.Request(GVZ_URL,headers=headers)
            with urllib.request.urlopen(req,timeout=8) as res:
                raw=res.read().decode("utf-8",errors="replace")
        value=parse_gvz_csv(raw)
        value["error"]=None
        _cache.update({"fetched_at":now,"value":value})
        return dict(value)
    except Exception as exc:
        if _cache["value"] is not None:
            value=dict(_cache["value"])
            value["error"]="refresh_failed"
            return value
        return {
            "gvz_regime":"UNKNOWN",
            "gvz":None,
            "error":type(exc).__name__,
            "source":"CBOE_GVZ_GLD_OPTIONS_PROXY",
            "proxy_note":"GLD_options_implied_volatility_not_CME_gold_futures",
        }


def analyze(m15, gvz=None):
    rv=realised_context(m15)
    gvz=fetch_gvz() if gvz is None else dict(gvz)
    rv_state=str(rv.get("rv_state") or "UNKNOWN")
    gvz_regime=str(gvz.get("gvz_regime") or "UNKNOWN")

    if rv_state in ("EXPLOSIVE","EXPANDING") and gvz_regime=="ELEVATED":
        state="STRESS_EXPANSION"
    elif rv_state=="COMPRESSED" and gvz_regime=="ELEVATED":
        state="PRICED_MOVE_COMPRESSION"
    elif rv_state in ("EXPLOSIVE","EXPANDING"):
        state="REALIZED_EXPANSION"
    elif gvz_regime=="ELEVATED":
        state="IMPLIED_ELEVATED"
    elif rv_state=="COMPRESSED":
        state="REALIZED_COMPRESSION"
    elif rv_state=="UNKNOWN" and gvz_regime=="UNKNOWN":
        state="UNKNOWN"
    else:
        state="NORMAL"

    return {
        "state":state,
        **rv,
        **gvz,
        "directional_signal":False,
    }
