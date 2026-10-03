"""Pure profit-protection policy for the Gigi REAL candidate.

This module does not talk to MT5 and cannot place or modify orders. It only
decides how much profit should be protected once a position is already open.
"""


def sniper_lock_usd(profit_usd: float):
    profit = float(profit_usd or 0.0)
    if profit >= 8.0:
        return 6.0
    if profit >= 6.0:
        return 4.0
    if profit >= 4.0:
        return 2.0
    if profit >= 2.0:
        return 1.0
    return None


def main_lock_usd(profit_usd: float, initial_risk_usd: float):
    """For MAIN trades, secure entry at +1R then trail roughly 1R behind."""
    profit = float(profit_usd or 0.0)
    risk = float(initial_risk_usd or 0.0)
    if risk <= 0 or profit < risk:
        return None

    raw_lock = max(0.10 * risk, profit - risk)
    step = max(0.10, 0.25 * risk)
    stepped = (raw_lock // step) * step
    return round(max(0.10 * risk, stepped), 2)


def desired_lock_usd(mode: str, profit_usd: float, initial_risk_usd: float = 0.0):
    mode = str(mode or "SNIPER").upper()
    if mode == "MAIN":
        return main_lock_usd(profit_usd, initial_risk_usd)
    return sniper_lock_usd(profit_usd)
