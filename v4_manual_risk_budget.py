"""Manual-only XAUUSD risk budget advisor.

No broker execution, no assumed lot contract size, and no guarantee of fills.
A broker-confirmed contract size and account currency conversion are required.
"""
import math
from decimal import Decimal, ROUND_FLOOR


def manual_risk_budget(*, side, entry, stop, risk_budget_usd,
                       contract_oz_per_lot=None, usd_per_quote_unit=None,
                       lot_step=None, min_lot=None, max_lot=None):
    """Return a conservative lot ceiling or WAIT when broker specs are missing.

    For XAUUSD quoted in USD, usd_per_quote_unit is 1.0. The caller must
    verify this and the contract size with the actual trading account.
    Rounding always goes DOWN to the broker lot step; never up to min lot.
    """
    if side not in ("BUY", "SELL"):
        return {"status": "WAIT", "reason": "invalid_side", "manual_only": True}
    raw = (entry, stop, risk_budget_usd, contract_oz_per_lot,
           usd_per_quote_unit, lot_step, min_lot, max_lot)
    if any(v is None for v in raw):
        return {"status": "WAIT", "reason": "broker_contract_or_currency_unverified", "manual_only": True}
    try:
        entry, stop, budget, contract, conversion, step, minimum, maximum = map(float, raw)
        if not all(math.isfinite(v) and v > 0 for v in (entry, stop, budget, contract,
                                                        conversion, step, minimum, maximum)):
            raise ValueError("nonpositive or nonfinite")
        if minimum > maximum or step > maximum:
            raise ValueError("invalid lot constraints")
        if (side == "BUY" and stop >= entry) or (side == "SELL" and stop <= entry):
            return {"status": "WAIT", "reason": "invalid_stop_direction", "manual_only": True}
        risk_per_lot = abs(entry - stop) * contract * conversion
        if risk_per_lot <= 0:
            raise ValueError("zero risk")
        # Compute the cap from decimal inputs, avoiding binary-float overestimation.
        d_entry, d_stop, d_budget, d_contract, d_conversion, d_step, _, d_max = (
            Decimal(str(v)) for v in raw)
        d_risk_per_lot = abs(d_entry - d_stop) * d_contract * d_conversion
        cap = min(d_max, d_budget / d_risk_per_lot)
        # Step multiples anchored at zero: conservative when min lot is not a multiple.
        # Decimal floor avoids rounding UP across a tight risk boundary.
        # Never add a tolerance to the risk budget: even a tiny excess is unsafe.
        units = int((cap / d_step).to_integral_value(rounding=ROUND_FLOOR))
        lot = float(Decimal(units) * Decimal(str(step)))
        if lot < minimum or lot <= 0:
            return {"status": "WAIT", "reason": "minimum_lot_exceeds_risk_budget",
                    "risk_per_lot_usd": round(risk_per_lot, 6), "manual_only": True}
        return {"status": "ADVISORY", "lot_ceiling": round(lot, 8),
                "estimated_stop_risk_usd": round(lot * risk_per_lot, 6),
                "risk_per_lot_usd": round(risk_per_lot, 6),
                "risk_budget_usd": budget, "manual_only": True,
                "note": "Excludes spread, slippage, commission, gaps and execution costs."}
    except (TypeError, ValueError, OverflowError):
        return {"status": "WAIT", "reason": "invalid_risk_inputs", "manual_only": True}
