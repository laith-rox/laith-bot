"""Performance metrics for research comparisons.

Metrics are descriptive.  No metric here is treated as a forecast of future
profitability.  The functions intentionally work on R-multiples so candidate
strategies with different dollar stop distances remain comparable.
"""
import math
import random


def max_drawdown(values):
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def longest_loss_streak(values):
    current = longest = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def summarize_r(values):
    measured = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if not measured:
        return {
            "measured": 0, "net_r": 0.0, "mean_r": None, "median_r": None,
            "wins": 0, "losses": 0, "win_rate": None, "profit_factor": None,
            "max_drawdown_r": 0.0, "longest_loss_streak": 0,
        }
    ordered = sorted(measured)
    n = len(ordered)
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    wins = [v for v in measured if v > 0]
    losses = [v for v in measured if v < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    return {
        "measured": n,
        "net_r": sum(measured),
        "mean_r": sum(measured) / n,
        "median_r": median,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n,
        "profit_factor": (gross_win / gross_loss if gross_loss > 0 else None),
        "max_drawdown_r": max_drawdown(measured),
        "longest_loss_streak": longest_loss_streak(measured),
    }


def block_bootstrap_mean_ci(values, block=5, samples=2000, seed=73):
    """Simple moving-block bootstrap CI for mean R.

    This is not a proof of profitability.  Blocking preserves some local serial
    dependence that an IID bootstrap would ignore.
    """
    values = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    n = len(values)
    if n < max(10, block * 2):
        return None
    block = max(1, min(block, n))
    chunks = [values[i:i + block] for i in range(0, n - block + 1)]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        sample = []
        while len(sample) < n:
            sample.extend(rng.choice(chunks))
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * (samples - 1))]
    hi = means[int(0.975 * (samples - 1))]
    return {"mean_r_95pct_low": lo, "mean_r_95pct_high": hi, "samples": samples, "block": block}


def grouped_trade_metrics(trades, key):
    groups = {}
    for trade in trades:
        label = trade.get(key, "UNKNOWN")
        groups.setdefault(label, []).append(trade.get("r"))
    return {label: summarize_r(values) for label, values in sorted(groups.items())}
