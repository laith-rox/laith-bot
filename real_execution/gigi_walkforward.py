"""Chronological price-only walk-forward research for Gigi.

This module reconstructs the current technical/structure signal engine using
only broker bars that would have been available at each historical decision
time. External slow feeds (CFTC, ETF, options, yields, news) are deliberately
excluded because replaying today's values into old bars would be look-ahead.

Research only: never sends or modifies orders.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import deque
from datetime import datetime, timezone

import gigi_clock
import gigi_evaluation
import gigi_replay
import real_analysis_engine as engine

ENTRY_START_MINUTE = 5 * 60
ENTRY_END_MINUTE = 20 * 60


def _epoch(row):
    raw=str((row or {}).get("datetime") or "").replace("Z","+00:00")
    dt=datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


def session_allowed(bar_datetime):
    minute=gigi_clock.local_minute(bar_datetime)
    return ENTRY_START_MINUTE <= minute < ENTRY_END_MINUTE


def _slice_through(rows, epochs, cutoff, count):
    idx=bisect_right(epochs, cutoff)-1
    if idx < 0:
        return []
    return rows[max(0,idx-count+1):idx+1]


def _closed_after_gap(rows, expected_seconds):
    try:
        normalized=engine.normalize_rows(rows)
    except Exception:
        return 0
    return engine._rows_after_last_gap(normalized, expected_seconds)


def _signal_from_history(m5_raw, m15_raw, h4_raw):
    m5=engine.normalize_rows(m5_raw)
    m15=engine.normalize_rows(m15_raw)
    h4=engine.normalize_rows(h4_raw)

    signal=engine.compute_signal(m5_raw)
    mtf=engine.analyze_structure(m5,m15,h4)
    signal=engine.apply_main_structure(signal,mtf)
    health={
        "client_state_fresh":True,
        "effective_risk_budget_usd":3.0,
        "strong_risk_budget_usd":15.0,
        "main_position_risk_usd":0.0,
        "sniper_position_risk_usd":0.0,
        "total_position_risk_usd":0.0,
    }
    signal=engine.recover_m15_continuation(signal,health)
    signal=engine.recover_strong_structural_entry(signal,health)
    return signal


def spread_cost_r(row, point, risk_distance):
    try:
        spread_points=max(0.0,float((row or {}).get("spread") or 0.0))
        risk=float(risk_distance)
        if risk <= 0:
            return 0.0
        return spread_points*float(point)/risk
    except Exception:
        return 0.0


def apply_cost(outcome, cost_r):
    out=dict(outcome or {})
    if out.get("close_r") is None:
        out["net_close_r"]=None
    else:
        out["net_close_r"]=round(float(out["close_r"])-max(0.0,float(cost_r)),4)
    out["spread_cost_r"]=round(max(0.0,float(cost_r)),4)
    return out


def walk_forward(m5_rows, m15_rows, h4_rows, point=0.01, max_signals_per_hour=6):
    m5=list(m5_rows or [])
    m15=list(m15_rows or [])
    h4=list(h4_rows or [])
    if len(m5)<160 or len(m15)<80 or len(h4)<35:
        return []

    m15_epochs=[_epoch(x) for x in m15]
    h4_epochs=[_epoch(x) for x in h4]
    observations=[]
    published=deque()

    # i is the last CLOSED M5 bar. i+1 is treated as the then-active bar and
    # is included only so normalize_rows can discard it exactly as live does.
    for i in range(100,len(m5)-gigi_evaluation.MAIN_HORIZON_BARS-2):
        active_epoch=_epoch(m5[i+1])
        m5_raw=m5[max(0,i-99):i+2]
        m15_raw=_slice_through(m15,m15_epochs,active_epoch,100)
        h4_raw=_slice_through(h4,h4_epochs,active_epoch,80)
        if len(m15_raw)<31 or len(h4_raw)<31:
            continue
        try:
            # Mirror live reopen warm-up without using historical "now".
            if _closed_after_gap(m5_raw,5*60)<3:
                continue
            if _closed_after_gap(m15_raw,15*60)<1:
                continue
            signal=_signal_from_history(m5_raw,m15_raw,h4_raw)
        except Exception:
            continue

        side=str(signal.get("side") or "").upper()
        if side not in ("BUY","SELL"):
            continue
        bar=str(signal.get("bar") or "")
        if not bar or not session_allowed(bar):
            continue
        if str(signal.get("mode") or "").upper()=="MAIN" and not engine.native_h4_reopen_ready(h4_raw):
            continue

        risk=float(signal.get("risk_distance") or 0.0)
        target_r=float(signal.get("target_r") or 0.0)
        entry=float(signal.get("reference_close") or 0.0)
        if entry<=0 or risk<=0 or target_r<=0:
            continue

        # Mirror the worker's six-per-hour publication cap chronologically.
        now_epoch=_epoch(m5[i])
        while published and now_epoch-published[0]>=3600:
            published.popleft()
        if len(published)>=int(max_signals_per_hour):
            continue

        future=m5[i+1:i+1+gigi_evaluation.MAIN_HORIZON_BARS]
        outcome=gigi_evaluation.evaluate(side,entry,risk,target_r,future,signal.get("mode"))
        if not outcome.get("resolved"):
            continue
        cost=spread_cost_r(m5[i],point,risk)
        result=apply_cost(outcome,cost)
        observations.append({
            "time":now_epoch,
            "bar":bar,
            "side":side,
            "mode":str(signal.get("mode") or "UNKNOWN").upper(),
            "reason":str(signal.get("reason") or ""),
            "score":int(signal.get("score") or 0),
            "entry":entry,
            "risk_distance":risk,
            "target_r":target_r,
            **result,
        })
        published.append(now_epoch)
    return observations


def _net_summary(observations):
    transformed=[]
    for row in observations or []:
        if row.get("net_close_r") is None:
            continue
        copy=dict(row)
        copy["close_r"]=float(row["net_close_r"])
        transformed.append(copy)
    return gigi_replay.summarize(transformed)


def multi_window_stability(window_summaries, min_per_window=20, required_windows=3):
    """Conservative stability label across independent chronological windows.

    Every required window must have enough observations. One missing/small
    window is not silently ignored because that can turn sparse evidence into
    fake stability.
    """
    rows=list(window_summaries or [])
    if len(rows) < int(required_windows):
        return {"status":"INSUFFICIENT_WINDOWS","qualified":False}
    rows=rows[:int(required_windows)]
    if any(int((row or {}).get("n") or 0) < int(min_per_window) for row in rows):
        return {
            "status":"INSUFFICIENT_PER_WINDOW",
            "qualified":False,
            "min_per_window":int(min_per_window),
        }
    means=[float((row or {}).get("mean_r") or 0.0) for row in rows]
    if all(x>0 for x in means):
        status="STABLE_POSITIVE"
    elif all(x<0 for x in means):
        status="STABLE_NEGATIVE"
    else:
        status="UNSTABLE"
    return {
        "status":status,
        "qualified":True,
        "means":[round(x,4) for x in means],
        "min_per_window":int(min_per_window),
    }


def report(observations):
    rows=list(observations or [])
    split=gigi_replay.chronological_split(rows,0.70)
    return {
        "n":len(rows),
        "gross":gigi_replay.summarize(rows),
        "spread_adjusted":_net_summary(rows),
        "train_spread_adjusted":_net_summary(split["train"]),
        "holdout_spread_adjusted":_net_summary(split["holdout"]),
        "by_mode":{
            k:_net_summary(v)
            for k,v in (
                ("MAIN",[x for x in rows if x.get("mode")=="MAIN"]),
                ("SNIPER",[x for x in rows if x.get("mode")=="SNIPER"]),
            )
        },
        "by_reason":{
            k:_net_summary([x for x in rows if x.get("reason")==k])
            for k in sorted({str(x.get("reason") or "") for x in rows})
        },
        "note":"price_only_chronological_walk_forward_external_context_excluded",
    }
