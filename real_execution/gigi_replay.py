"""Conservative price-path replay helpers for Gigi research.

This is a research/backtest utility only. It does not place orders and it does
not use current external feeds to reconstruct historical macro/ETF/options
states. If both stop and target are touched in the same bar, stop is counted
first to avoid optimistic intrabar assumptions.
"""
from __future__ import annotations


def first_touch_outcome(side, entry, risk_distance, target_r, future_rows, max_bars=24):
    side=str(side or "").upper()
    entry=float(entry)
    risk=float(risk_distance)
    target_r=float(target_r)
    rows=list(future_rows or [])[:int(max_bars)]
    if side not in ("BUY","SELL") or entry<=0 or risk<=0 or target_r<=0 or not rows:
        return {
            "resolved":False,
            "outcome":"INVALID",
            "close_r":None,
            "mfe_r":None,
            "mae_r":None,
            "bars":0,
        }

    if side=="BUY":
        stop=entry-risk
        target=entry+risk*target_r
    else:
        stop=entry+risk
        target=entry-risk*target_r

    mfe=0.0
    mae=0.0
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

        # Conservative ordering when bar OHLC cannot reveal which touched first.
        if stop_hit:
            return {
                "resolved":True,
                "outcome":"STOP",
                "close_r":-1.0,
                "mfe_r":round(mfe,4),
                "mae_r":round(mae,4),
                "bars":i,
            }
        if target_hit:
            return {
                "resolved":True,
                "outcome":"TARGET",
                "close_r":round(target_r,4),
                "mfe_r":round(mfe,4),
                "mae_r":round(mae,4),
                "bars":i,
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
    }


def summarize(observations):
    rows=[x for x in (observations or []) if x.get("resolved") and x.get("close_r") is not None]
    if not rows:
        return {
            "n":0,
            "mean_r":0.0,
            "median_r":0.0,
            "win_rate":0.0,
            "target_rate":0.0,
            "stop_rate":0.0,
            "max_drawdown_r":0.0,
        }
    vals=[float(x["close_r"]) for x in rows]
    ordered=sorted(vals)
    n=len(vals)
    median=(ordered[n//2] if n%2 else (ordered[n//2-1]+ordered[n//2])/2.0)
    wins=[v for v in vals if v>0]
    losses=[v for v in vals if v<0]
    avg_win=(sum(wins)/len(wins)) if wins else 0.0
    avg_loss=(sum(losses)/len(losses)) if losses else 0.0
    loss_abs=abs(avg_loss)
    payoff=(avg_win/loss_abs) if avg_win>0 and loss_abs>0 else None
    gross_profit=sum(wins)
    gross_loss=abs(sum(losses))
    profit_factor=(gross_profit/gross_loss) if gross_loss>0 else None
    breakeven_win_rate=(loss_abs/(avg_win+loss_abs)) if avg_win>0 and loss_abs>0 else None
    equity=0.0; peak=0.0; max_dd=0.0
    for v in vals:
        equity+=v
        peak=max(peak,equity)
        max_dd=max(max_dd,peak-equity)
    return {
        "n":n,
        "mean_r":round(sum(vals)/n,4),
        "median_r":round(median,4),
        "win_rate":round(sum(v>0 for v in vals)/n,4),
        "avg_win_r":round(avg_win,4),
        "avg_loss_r":round(avg_loss,4),
        "payoff_ratio":None if payoff is None else round(payoff,4),
        "profit_factor":None if profit_factor is None else round(profit_factor,4),
        "breakeven_win_rate":None if breakeven_win_rate is None else round(breakeven_win_rate,4),
        "target_rate":round(sum(x.get("outcome")=="TARGET" for x in rows)/n,4),
        "stop_rate":round(sum(x.get("outcome")=="STOP" for x in rows)/n,4),
        "max_drawdown_r":round(max_dd,4),
        "mean_mfe_r":round(sum(float(x.get("mfe_r") or 0) for x in rows)/n,4),
        "mean_mae_r":round(sum(float(x.get("mae_r") or 0) for x in rows)/n,4),
    }


def chronological_split(observations, train_fraction=0.70):
    rows=sorted(list(observations or []),key=lambda x:float(x.get("time") or 0))
    if not rows:
        return {"train":[],"holdout":[]}
    split=max(1,min(len(rows)-1,int(round(len(rows)*float(train_fraction))))) if len(rows)>1 else 1
    return {"train":rows[:split],"holdout":rows[split:]}


def grouped_summary(observations, key):
    groups={}
    for row in observations or []:
        value=str(row.get(key) or "UNKNOWN").upper()
        groups.setdefault(value,[]).append(row)
    return {name:summarize(rows) for name,rows in sorted(groups.items())}
