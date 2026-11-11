"""Candle-aligned V4 analysis scheduling, independent of processing duration."""
import math


def next_official_cycle(epoch, interval=900):
    """Next settled UTC candle boundary (20s after a 5m multiple).

    Round custom intervals up to a 5m multiple so a strict 120s closed-bar
    freshness gate is reachable. Never accumulate fetch/analysis time as drift.
    """
    width = max(300, math.ceil(max(1, interval) / 300) * 300)
    target = math.floor(epoch / width) * width + 20
    if target <= epoch:
        target += width
    return target
