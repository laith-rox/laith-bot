"""Fast-flow stress context for Gigi shadow analysis.

Detects one-sided cascade / squeeze behaviour from broker-native CLOSED M5 bars:
directional persistence, movement relative to prior noise, range expansion,
close location, and tick-volume participation. Tick volume is a broker activity
proxy, not centralized exchange volume.

This module never places orders and never treats a cascade as a fresh entry by
itself. A cascade may be continuation, liquidation, short covering, or the last
leg before exhaustion.
"""
from __future__ import annotations

from statistics import median


def _range(row):
    return max(0.0, float(row["high"]) - float(row["low"]))


def _close_location(row):
    high=float(row["high"]); low=float(row["low"]); close=float(row["close"])
    span=max(high-low,1e-12)
    return max(0.0,min(1.0,(close-low)/span))


def _median_positive(values):
    vals=[float(x) for x in values if float(x)>0]
    return median(vals) if vals else 0.0


def analyze(m5, recent_bars=4):
    rows=list(m5 or [])
    if len(rows) < 30:
        return {
            "state":"UNKNOWN",
            "direction":"NONE",
            "cascade_score":0,
            "directional_signal":False,
            "note":"insufficient_closed_m5_history",
        }

    recent=rows[-recent_bars:]
    base=rows[-(recent_bars+24):-recent_bars]
    if len(recent)<recent_bars or len(base)<12:
        return {
            "state":"UNKNOWN",
            "direction":"NONE",
            "cascade_score":0,
            "directional_signal":False,
            "note":"insufficient_baseline",
        }

    baseline_range=_median_positive([_range(r) for r in base])
    if baseline_range <= 0:
        return {
            "state":"UNKNOWN",
            "direction":"NONE",
            "cascade_score":0,
            "directional_signal":False,
            "note":"zero_baseline_range",
        }

    baseline_volume=_median_positive([float(r.get("tick_volume") or 0) for r in base])
    recent_ranges=[_range(r) for r in recent]
    recent_range_med=_median_positive(recent_ranges)
    range_ratio=recent_range_med/baseline_range if baseline_range else 0.0

    recent_vol=_median_positive([float(r.get("tick_volume") or 0) for r in recent])
    volume_ratio=(recent_vol/baseline_volume) if baseline_volume>0 else 1.0

    first_open=float(recent[0]["open"])
    last_close=float(recent[-1]["close"])
    net=last_close-first_open
    net_atr=net/baseline_range

    up=sum(float(r["close"])>float(r["open"]) for r in recent)
    down=sum(float(r["close"])<float(r["open"]) for r in recent)
    close_loc=_close_location(recent[-1])

    up_checks=[
        net_atr >= 2.2,
        up >= recent_bars-1,
        range_ratio >= 1.15,
        volume_ratio >= 1.05,
        close_loc >= 0.70,
    ]
    down_checks=[
        net_atr <= -2.2,
        down >= recent_bars-1,
        range_ratio >= 1.15,
        volume_ratio >= 1.05,
        close_loc <= 0.30,
    ]
    up_score=sum(bool(x) for x in up_checks)
    down_score=sum(bool(x) for x in down_checks)

    if up_score >= 4 and up_checks[0] and up_checks[1]:
        state="UP_SQUEEZE"
        direction="UP"
        cascade_score=up_score
    elif down_score >= 4 and down_checks[0] and down_checks[1]:
        state="DOWN_CASCADE"
        direction="DOWN"
        cascade_score=down_score
    elif net_atr >= 1.5 and up >= recent_bars-1:
        state="FAST_UP_IMPULSE"
        direction="UP"
        cascade_score=up_score
    elif net_atr <= -1.5 and down >= recent_bars-1:
        state="FAST_DOWN_IMPULSE"
        direction="DOWN"
        cascade_score=down_score
    else:
        state="BALANCED"
        direction="NONE"
        cascade_score=max(up_score,down_score)

    return {
        "state":state,
        "direction":direction,
        "cascade_score":int(cascade_score),
        "up_checks":int(up_score),
        "down_checks":int(down_score),
        "net_move_noise_units":round(float(net_atr),3),
        "recent_range_ratio":round(float(range_ratio),3),
        "tick_volume_ratio":round(float(volume_ratio),3),
        "up_bars":int(up),
        "down_bars":int(down),
        "last_close_location":round(float(close_loc),3),
        "directional_signal":False,
        "note":"m5_flow_stress_context_tick_volume_proxy_not_entry_signal",
    }
