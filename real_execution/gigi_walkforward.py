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
import gigi_profit_protection
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


def session_bucket(bar_datetime):
    minute=gigi_clock.local_minute(bar_datetime)
    if minute < ENTRY_START_MINUTE or minute >= ENTRY_END_MINUTE:
        return "OUTSIDE"
    if minute < 10*60:
        return "EARLY_05_10"
    if minute < 13*60:
        return "LONDON_10_13"
    if minute < 15*60+20:
        return "MIDDAY_13_1520"
    if minute < 18*60:
        return "US_1520_18"
    return "LATE_18_20"


def h4_alignment(side, h4_bias):
    side=str(side or "").upper()
    bias=str(h4_bias or "NEUTRAL").upper()
    if bias=="NEUTRAL" or side not in ("BUY","SELL"):
        return "NEUTRAL"
    if (side=="BUY" and bias=="UP") or (side=="SELL" and bias=="DOWN"):
        return "ALIGNED"
    return "COUNTER"


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


def protected_outcome(side, entry, risk_distance, target_r, future_rows, mode,
                      usd_per_price_unit=1.0):
    """Replay the candidate profit-protection policy conservatively.

    New locks become active from the next bar because OHLC cannot reveal the
    intrabar ordering between a profit trigger and a reversal. This avoids
    optimistic use of information inside the same candle.
    """
    side=str(side or "").upper()
    entry=float(entry)
    risk=float(risk_distance)
    target_r=float(target_r)
    usd_per=max(0.0,float(usd_per_price_unit))
    horizon=gigi_evaluation.horizon_bars(mode)
    rows=list(future_rows or [])[:horizon]
    if side not in ("BUY","SELL") or entry<=0 or risk<=0 or target_r<=0 or usd_per<=0 or not rows:
        return {"resolved":False,"outcome":"INVALID","close_r":None,"mfe_r":None,"mae_r":None,"bars":0}

    initial_risk_usd=risk*usd_per
    stop=entry-risk if side=="BUY" else entry+risk
    target=entry+risk*target_r if side=="BUY" else entry-risk*target_r
    peak_profit_usd=0.0
    mfe=0.0
    mae=0.0
    protection_activated=False
    best_locked_usd=0.0

    for i,row in enumerate(rows,1):
        high=float(row["high"]); low=float(row["low"])
        if side=="BUY":
            mfe=max(mfe,(high-entry)/risk)
            mae=min(mae,(low-entry)/risk)
            stop_hit=low<=stop
            target_hit=high>=target
        else:
            mfe=max(mfe,(entry-low)/risk)
            mae=min(mae,(entry-high)/risk)
            stop_hit=high>=stop
            target_hit=low<=target

        # Conservative OHLC ordering: any already-active stop wins before target.
        if stop_hit:
            close_r=((stop-entry)/risk) if side=="BUY" else ((entry-stop)/risk)
            return {
                "resolved":True,
                "outcome":"PROTECTED_STOP" if close_r>0 else "STOP",
                "close_r":round(close_r,4),
                "mfe_r":round(mfe,4),
                "mae_r":round(mae,4),
                "bars":i,
                "protection_activated":protection_activated,
                "locked_usd_peak":round(best_locked_usd,2),
            }
        if target_hit:
            return {
                "resolved":True,
                "outcome":"TARGET",
                "close_r":round(target_r,4),
                "mfe_r":round(mfe,4),
                "mae_r":round(mae,4),
                "bars":i,
                "protection_activated":protection_activated,
                "locked_usd_peak":round(best_locked_usd,2),
            }

        favorable=(high-entry) if side=="BUY" else (entry-low)
        peak_profit_usd=max(peak_profit_usd,max(0.0,favorable)*usd_per)
        lock=gigi_profit_protection.desired_lock_usd(mode,peak_profit_usd,initial_risk_usd)
        if lock is not None:
            lock=max(0.0,float(lock))
            best_locked_usd=max(best_locked_usd,lock)
            lock_distance=best_locked_usd/usd_per
            candidate=entry+lock_distance if side=="BUY" else entry-lock_distance
            if side=="BUY":
                stop=max(stop,candidate)
            else:
                stop=min(stop,candidate)
            protection_activated=True

    if len(rows)<horizon:
        return {
            "resolved":False,
            "outcome":"PENDING",
            "bars":len(rows),
            "mfe_r":round(mfe,4),
            "mae_r":round(mae,4),
            "protection_activated":protection_activated,
            "locked_usd_peak":round(best_locked_usd,2),
        }

    final=float(rows[-1]["close"])
    close_r=((final-entry)/risk) if side=="BUY" else ((entry-final)/risk)
    return {
        "resolved":True,
        "outcome":"HORIZON",
        "close_r":round(close_r,4),
        "mfe_r":round(mfe,4),
        "mae_r":round(mae,4),
        "bars":len(rows),
        "protection_activated":protection_activated,
        "locked_usd_peak":round(best_locked_usd,2),
    }


def walk_forward(m5_rows, m15_rows, h4_rows, point=0.01, max_signals_per_hour=6,
                 usd_per_price_unit=1.0):
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
        static_outcome=gigi_evaluation.evaluate(side,entry,risk,target_r,future,signal.get("mode"))
        outcome=protected_outcome(
            side,entry,risk,target_r,future,signal.get("mode"),
            usd_per_price_unit=usd_per_price_unit,
        )
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
            "strength":int(engine.signal_strength(signal)),
            "h4_bias":str((signal.get("mtf") or {}).get("h4_bias") or "NEUTRAL").upper(),
            "h4_alignment":h4_alignment(side,(signal.get("mtf") or {}).get("h4_bias")),
            "session_bucket":session_bucket(bar),
            "entry":entry,
            "risk_distance":risk,
            "target_r":target_r,
            "static_outcome":static_outcome.get("outcome"),
            "static_close_r":static_outcome.get("close_r"),
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


def _static_net_summary(observations):
    transformed=[]
    for row in observations or []:
        if row.get("static_close_r") is None:
            continue
        copy=dict(row)
        copy["close_r"]=float(row["static_close_r"])-float(row.get("spread_cost_r") or 0.0)
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
        "static_spread_adjusted":_static_net_summary(rows),
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
        "by_session":{
            k:_net_summary([x for x in rows if x.get("session_bucket")==k])
            for k in sorted({str(x.get("session_bucket") or "UNKNOWN") for x in rows})
        },
        "by_strength":{
            str(k):_net_summary([x for x in rows if int(x.get("strength") or 0)==k])
            for k in sorted({int(x.get("strength") or 0) for x in rows})
        },
        "by_reason_h4":{
            f"{reason}|{bias}":_net_summary([
                x for x in rows
                if x.get("reason")==reason and x.get("h4_bias")==bias
            ])
            for reason,bias in sorted({
                (str(x.get("reason") or ""),str(x.get("h4_bias") or "NEUTRAL"))
                for x in rows
            })
        },
        "by_reason_h4_alignment":{
            f"{reason}|{alignment}":_net_summary([
                x for x in rows
                if x.get("reason")==reason and x.get("h4_alignment")==alignment
            ])
            for reason,alignment in sorted({
                (str(x.get("reason") or ""),str(x.get("h4_alignment") or "NEUTRAL"))
                for x in rows
            })
        },
        "note":"price_only_walk_forward_with_conservative_next_bar_profit_protection_external_context_excluded",
    }
