"""Empirical session research for Gigi.

Descriptive only. Given a long broker-native M15 history, summarize how gold
behaved by Palestine local hour. This does not choose BUY/SELL and never places
or authorizes orders. It is intended to stop us from hard-coding folklore about
"best hours" without checking the broker's own historical bars.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

UTC=timezone.utc
PALESTINE_TZ="Asia/Hebron"


def _dt(row):
    raw=(row or {}).get("datetime")
    if raw is None and (row or {}).get("time") is not None:
        return datetime.fromtimestamp(float(row["time"]),tz=UTC)
    value=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    if value.tzinfo is None:
        value=value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _pct(values):
    return 100.0*sum(values)/len(values) if values else None


def analyze(rows, timezone_name=PALESTINE_TZ, min_samples=80):
    rows=sorted(list(rows or []),key=_dt)
    if len(rows)<40:
        return {"state":"INSUFFICIENT","hours":{},"directional_signal":False}

    tz=ZoneInfo(timezone_name) if ZoneInfo is not None else UTC
    buckets=defaultdict(lambda:{"range":[],"move1h":[],"move4h":[],"cont1h":[]})
    for i in range(4,len(rows)-16):
        now=_dt(rows[i])
        # Require nearly continuous forward bars. Weekend/daily gaps must not
        # be interpreted as a giant session move.
        if (_dt(rows[i+4])-now).total_seconds() > 5*15*60:
            continue
        if (_dt(rows[i+16])-now).total_seconds() > 17*15*60:
            continue
        hour=now.astimezone(tz).hour
        cur=rows[i]
        close=float(cur["close"])
        high=float(cur["high"]); low=float(cur["low"])
        b=buckets[hour]
        b["range"].append(high-low)
        b["move1h"].append(abs(float(rows[i+4]["close"])-close))
        b["move4h"].append(abs(float(rows[i+16]["close"])-close))
        prev=close-float(rows[i-4]["close"])
        nxt=float(rows[i+4]["close"])-close
        if abs(prev)>1e-12 and abs(nxt)>1e-12:
            b["cont1h"].append(1 if prev*nxt>0 else 0)

    all_ranges=[x for b in buckets.values() for x in b["range"]]
    baseline=median(all_ranges) if all_ranges else 0.0
    out={}
    for hour,b in sorted(buckets.items()):
        n=len(b["range"])
        if not n:
            continue
        rng=median(b["range"])
        cont=_pct(b["cont1h"])
        if n < min_samples:
            quality="LOW_SAMPLE"
        else:
            quality="USABLE"
        ratio=(rng/baseline) if baseline>0 else 0.0
        if ratio>=1.30:
            activity="HIGH"
        elif ratio<=0.75:
            activity="LOW"
        else:
            activity="NORMAL"
        if cont is None:
            behavior="UNKNOWN"
        elif cont>=55.0:
            behavior="CONTINUATION_LEAN"
        elif cont<=45.0:
            behavior="REVERSAL_LEAN"
        else:
            behavior="MIXED"
        out[str(hour)]={
            "n":n,
            "median_m15_range":round(rng,3),
            "median_abs_1h_move":round(median(b["move1h"]),3),
            "median_abs_4h_move":round(median(b["move4h"]),3),
            "continuation_1h_pct":None if cont is None else round(cont,1),
            "activity":activity,
            "behavior":behavior,
            "quality":quality,
        }

    return {
        "state":"READY" if any(x["quality"]=="USABLE" for x in out.values()) else "LOW_SAMPLE",
        "timezone":timezone_name,
        "baseline_m15_range":round(baseline,3),
        "hours":out,
        "directional_signal":False,
        "execution_gate":False,
        "note":"historical_session_description_not_entry_signal_or_probability",
    }


def window_summary(profile, start_hour, end_hour):
    hours=(profile or {}).get("hours") or {}
    selected=[]
    for key,row in hours.items():
        h=int(key)
        inside=(start_hour<=h<end_hour) if start_hour<end_hour else (h>=start_hour or h<end_hour)
        if inside and row.get("quality")=="USABLE":
            selected.append((h,row))
    if not selected:
        return {"state":"INSUFFICIENT","start_hour":start_hour,"end_hour":end_hour}
    high=[h for h,row in selected if row.get("activity")=="HIGH"]
    continuation=[h for h,row in selected if row.get("behavior")=="CONTINUATION_LEAN"]
    reversal=[h for h,row in selected if row.get("behavior")=="REVERSAL_LEAN"]
    return {
        "state":"READY",
        "start_hour":start_hour,
        "end_hour":end_hour,
        "high_activity_hours":high,
        "continuation_lean_hours":continuation,
        "reversal_lean_hours":reversal,
        "directional_signal":False,
        "note":"window_description_only_not_trade_permission",
    }
