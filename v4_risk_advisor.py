"""V4 advisory-only capital protection; never places an order.

Contract size and tick value must come from verified broker symbol specifications.
Unknown inputs fail closed rather than guessing a lot size.
"""
import math


def risk_based_lot(*, equity, risk_percent, entry, stop, contract_size,
                   lot_step, min_lot, max_lot, max_risk_percent=1.0):
    """Return a conservative advisory lot and actual risk, or None.

    Assumes quote currency and account currency match. The caller must verify
    currency conversion separately; this is not a universal CFD pip formula.
    """
    values = (equity, risk_percent, entry, stop, contract_size, lot_step,
              min_lot, max_lot, max_risk_percent)
    try:
        values = tuple(float(x) for x in values)
    except (ValueError, TypeError):
        return None
    if not all(math.isfinite(x) for x in values):
        return None
    equity, pct, entry, stop, size, step, minimum, maximum, cap = values
    if (equity <= 0 or pct <= 0 or pct > cap or cap > 2 or
            entry <= 0 or stop <= 0 or entry == stop or size <= 0 or
            step <= 0 or minimum <= 0 or maximum < minimum):
        return None
    budget = equity * pct / 100
    loss_per_lot = abs(entry - stop) * size
    units = math.floor((budget / loss_per_lot + 1e-12) / step)
    lots = round(min(units * step, maximum), 8)
    if lots < minimum or lots * loss_per_lot > budget + 1e-8:
        return None
    return {"lot": lots, "risk_budget": round(budget, 2),
            "estimated_stop_loss": round(lots * loss_per_lot, 2),
            "risk_percent": pct, "manual_only": True}
