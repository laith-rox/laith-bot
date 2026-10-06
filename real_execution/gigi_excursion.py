"""Shadow excursion research for Gigi.

Summarizes MFE/MAE path behavior from already-resolved shadow observations.
This is research only: no order placement, no target/stop mutation, and no
automatic promotion. It is designed to answer questions such as "does this
setup usually reach +0.5R but fail before +1R?" without overfitting a handful
of trades.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

MIN_GROUP_SAMPLES = 30
GROUPS = ("mode", "reason", "setup_archetype", "session", "flow_stress_state")


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def _quantile(values, q):
    vals=sorted(float(x) for x in values)
    if not vals:
        return None
    if len(vals)==1:
        return vals[0]
    q=max(0.0,min(1.0,float(q)))
    pos=(len(vals)-1)*q
    lo=int(pos)
    hi=min(lo+1,len(vals)-1)
    frac=pos-lo
    return vals[lo]*(1-frac)+vals[hi]*frac


def summarize_values(rows, min_samples=MIN_GROUP_SAMPLES):
    rows=list(rows or [])
    n=len(rows)
    if n==0:
        return {"n":0,"status":"NO_DATA"}

    close_r=[_safe_float(x.get("close_r")) for x in rows]
    mfe=[_safe_float(x.get("mfe_r")) for x in rows]
    mae=[_safe_float(x.get("mae_r")) for x in rows]

    hit05=sum(x>=0.5 for x in mfe)/n
    hit10=sum(x>=1.0 for x in mfe)/n
    hit15=sum(x>=1.5 for x in mfe)/n
    hit20=sum(x>=2.0 for x in mfe)/n
    touch_stop=sum(x<=-1.0 for x in mae)/n

    if n < min_samples:
        posture="INSUFFICIENT_SAMPLE"
    elif hit05>=0.70 and hit10<0.45:
        posture="EARLY_PROFIT_HEAVY"
    elif hit10>=0.60 and hit15>=0.30:
        posture="EXTENSION_CAPABLE"
    elif touch_stop>=0.50 and hit10<0.50:
        posture="TWO_SIDED_NOISY"
    else:
        posture="MIXED_PATH"

    return {
        "n":n,
        "status":"CALIBRATED" if n>=min_samples else "INSUFFICIENT_SAMPLE",
        "path_posture":posture,
        "mean_close_r":round(sum(close_r)/n,4),
        "median_mfe_r":round(median(mfe),4),
        "median_mae_r":round(median(mae),4),
        "mfe_q25_r":round(_quantile(mfe,0.25),4),
        "mfe_q75_r":round(_quantile(mfe,0.75),4),
        "mae_q25_r":round(_quantile(mae,0.25),4),
        "mae_q75_r":round(_quantile(mae,0.75),4),
        "hit_0_5r":round(hit05,4),
        "hit_1_0r":round(hit10,4),
        "hit_1_5r":round(hit15,4),
        "hit_2_0r":round(hit20,4),
        "touch_minus_1r":round(touch_stop,4),
        "note":"shadow_excursion_research_not_exit_rule",
    }


def report(observations, min_samples=MIN_GROUP_SAMPLES):
    observations=[dict(x) for x in (observations or [])]
    groups={}
    groups["ALL"]=summarize_values(observations,min_samples=min_samples)

    for dimension in GROUPS:
        buckets=defaultdict(list)
        for obs in observations:
            key=str(obs.get(dimension) or "UNKNOWN").upper()
            buckets[key].append(obs)
        groups[dimension]={
            key:summarize_values(rows,min_samples=min_samples)
            for key,rows in sorted(buckets.items())
        }

    return {
        "resolved_observations":len(observations),
        "minimum_group_samples":int(min_samples),
        "groups":groups,
        "directional_signal":False,
        "execution_gate":False,
        "note":"excursion_path_research_only_no_auto_stop_or_target_change",
    }
