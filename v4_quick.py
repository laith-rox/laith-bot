"""Five-minute quick paper candidates for Laith V4.

Quick candidates are intentionally separate from the strict V4 paper strategy.
They are research-only, use the same seven observable checks from the baseline
analyzer, and never create broker orders.  A strength label means rule completion,
not a calibrated probability of profit.
"""
from copy import deepcopy
import hashlib
import math


CONDITION_NAMES = (
    "اتجاه 15د EMA20/50",
    "اتجاه الساعة EMA20/50",
    "زخم MACD",
    "نطاق RSI المناسب",
    "موقع السعر من EMA20",
    "اتجاه شمعة 15د",
    "السعر غير متمدد",
)


def strength_label(score):
    if score >= 6:
        return "قوية"
    if score == 5:
        return "متوسطة"
    return "ضعيفة"


def leading_side(decision):
    """Return a quick side only when one side has usable rule dominance."""
    try:
        buy = int(decision.get("buy", 0))
        sell = int(decision.get("sell", 0))
    except (TypeError, ValueError):
        return None
    if max(buy, sell) < 4 or abs(buy - sell) < 2:
        return None
    return "BUY" if buy > sell else "SELL"


def _opposite_correction(side, correction):
    direction = (correction or {}).get("direction")
    return ((side == "BUY" and direction == "DOWN")
            or (side == "SELL" and direction == "UP"))


def build_quick(decision, now, quote_price=None, lifetime_seconds=1200):
    """Build one quick paper setup from the latest V4 analysis.

    Strict V4 candidates take precedence.  Quick candidates are also blocked by
    extreme volatility, failed breaks, and triggered strong opposite corrections.
    """
    if decision.get("side") in ("BUY", "SELL"):
        return None
    side = leading_side(decision)
    if side is None:
        return None

    checks = (decision.get("checks") or {}).get(side)
    if not isinstance(checks, (list, tuple)) or len(checks) != 7:
        return None
    checks = [bool(x) for x in checks]
    score = sum(checks)
    if score < 4:
        return None

    research = decision.get("v4") or {}
    if research.get("volatility_regime") == "EXTREME":
        return None
    if research.get("breakout_state") == "FAILED_BREAK":
        return None
    correction = research.get("correction") or {}
    if (correction.get("triggered") and correction.get("strength") == "STRONG"
            and _opposite_correction(side, correction)):
        return None

    try:
        atr = float(decision["atr"])
        price = float(quote_price if quote_price is not None else decision["price"])
        rsi = float(decision.get("rsi"))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (atr, price, rsi)) or atr <= 0 or price <= 0:
        return None

    # A deliberately small, testable paper scalp envelope.  It is not claimed to
    # be optimal; V4 records outcomes so the rule can later be kept, changed, or removed.
    risk = min(5.0, max(2.0, 0.60 * atr))
    rr = 1.50
    direction = 1 if side == "BUY" else -1
    stop = price - direction * risk
    target = price + direction * risk * rr
    slot = int(now.timestamp() // 300)
    quick_id = hashlib.sha256(f"V4Q:{slot}:{side}".encode()).hexdigest()[:12]
    conditions = [
        {"name": name, "ok": ok}
        for name, ok in zip(CONDITION_NAMES, checks)
    ]
    return {
        "id": quick_id,
        "generation": "V4",
        "kind": "QUICK",
        "paper_only": True,
        "side": side,
        "entry": price,
        "initial_sl": stop,
        "stop": stop,
        "target": target,
        "rr": rr,
        "risk": risk,
        "score": score,
        "total": 7,
        "condition_percent": round(score / 7 * 100),
        "strength": strength_label(score),
        "conditions": conditions,
        "rsi": rsi,
        "session": research.get("session"),
        "volatility_regime": research.get("volatility_regime"),
        "volatility_percentile": research.get("volatility_percentile"),
        "macro_alignment": research.get("macro_alignment"),
        "breakout_state": research.get("breakout_state"),
        "created": now.timestamp(),
        "announced": now.timestamp(),
        "expires": now.timestamp() + lifetime_seconds,
        "last_end": None,
        "status": "active",
        "outcome": None,
        "exit": None,
        "closed": None,
        "r": None,
    }


def advance_quick(original, bars, now):
    """Advance a quick paper setup using closed 5-minute OHLC bars.

    If stop and target occur in the same candle, ordering is unknown and the result
    is excluded rather than counted as a win.  Unresolved setups expire using the
    latest closed price available at or before expiry.
    """
    trade = deepcopy(original)
    if trade.get("status") != "active":
        return trade
    direction = 1 if trade["side"] == "BUY" else -1
    announced = float(trade["announced"])
    expires = float(trade["expires"])
    last_eligible = None

    for bar in bars:
        end = bar.end.timestamp()
        if end <= (trade.get("last_end") or announced):
            continue
        if end > expires:
            break
        last_eligible = bar
        stop_hit = bar.low <= trade["stop"] if direction == 1 else bar.high >= trade["stop"]
        target_hit = bar.high >= trade["target"] if direction == 1 else bar.low <= trade["target"]
        trade["last_end"] = end
        if stop_hit and target_hit:
            trade.update(status="closed", outcome="AMBIGUOUS", exit=None,
                         closed=end, r=None)
            return trade
        if stop_hit:
            trade.update(status="closed", outcome="STOP", exit=trade["stop"],
                         closed=end, r=-1.0)
            return trade
        if target_hit:
            trade.update(status="closed", outcome="TARGET", exit=trade["target"],
                         closed=end, r=float(trade["rr"]))
            return trade

    if now.timestamp() >= expires:
        if last_eligible is None:
            eligible = [b for b in bars if announced < b.end.timestamp() <= expires]
            last_eligible = eligible[-1] if eligible else None
        if last_eligible is not None:
            exit_price = last_eligible.close
            r = direction * (exit_price - trade["entry"]) / trade["risk"]
            trade.update(status="closed", outcome="TIME", exit=exit_price,
                         closed=expires, r=r)
    return trade


def cancel_quick(original, now, reason="OFFICIAL_SUPERSEDED"):
    trade = deepcopy(original)
    if trade.get("status") == "active":
        trade.update(status="closed", outcome=reason, closed=now.timestamp(), r=None)
    return trade
