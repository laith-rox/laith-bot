"""Liquidity-map context for Gigi REAL shadow analysis.

Pure price-action analysis. Detects nearby liquidity pools and confirmed sweeps
using broker-native candles. It never places or modifies orders.
"""
from __future__ import annotations


def _atr(rows, period=14):
    if len(rows) < 2:
        return 0.0
    trs=[]
    start=max(1,len(rows)-period)
    for i in range(start,len(rows)):
        prev=float(rows[i-1]["close"])
        high=float(rows[i]["high"])
        low=float(rows[i]["low"])
        trs.append(max(high-low,abs(high-prev),abs(low-prev)))
    return sum(trs)/len(trs) if trs else 0.0


def _cluster_count(values, level, tolerance):
    return sum(1 for value in values if abs(float(value)-float(level)) <= tolerance)


def analyze(m5, m15=None):
    rows=list(m5 or [])
    if len(rows) < 24:
        return {
            "event":"UNKNOWN",
            "pressure":"NEUTRAL",
            "buy_side_pool":None,
            "sell_side_pool":None,
            "equal_high_count":0,
            "equal_low_count":0,
        }

    atr=max(_atr(rows,14),1e-9)
    lookback=rows[-21:-1]
    last=rows[-1]
    highs=[float(r["high"]) for r in lookback]
    lows=[float(r["low"]) for r in lookback]
    buy_pool=max(highs)
    sell_pool=min(lows)
    close=float(last["close"])
    high=float(last["high"])
    low=float(last["low"])
    tolerance=max(0.05,0.12*atr)
    sweep_buffer=max(0.02,0.04*atr)

    buy_side_sweep=high > buy_pool + sweep_buffer and close < buy_pool
    sell_side_sweep=low < sell_pool - sweep_buffer and close > sell_pool

    equal_high_count=_cluster_count(highs,buy_pool,tolerance)
    equal_low_count=_cluster_count(lows,sell_pool,tolerance)

    if sell_side_sweep and not buy_side_sweep:
        event="SELL_SIDE_SWEEP"
        pressure="BULLISH"
    elif buy_side_sweep and not sell_side_sweep:
        event="BUY_SIDE_SWEEP"
        pressure="BEARISH"
    elif buy_side_sweep and sell_side_sweep:
        event="TWO_SIDED_SWEEP"
        pressure="NEUTRAL"
    else:
        event="NONE"
        pressure="NEUTRAL"

    return {
        "event":event,
        "pressure":pressure,
        "buy_side_pool":round(buy_pool,5),
        "sell_side_pool":round(sell_pool,5),
        "distance_to_buy_pool_atr":round((buy_pool-close)/atr,3),
        "distance_to_sell_pool_atr":round((close-sell_pool)/atr,3),
        "equal_high_count":equal_high_count,
        "equal_low_count":equal_low_count,
        "pool_tolerance":round(tolerance,5),
        "method":"swing_pool_and_close_back_sweep",
    }
