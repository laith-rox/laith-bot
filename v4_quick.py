"""Five-minute quick paper candidates for Laith V4.

Quick candidates are intentionally separate from the strict V4 paper strategy.
They are research-only, use the same seven observable checks from the baseline
analyzer, and never create broker orders. A strength label means rule completion,
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


def _checks(decision, side):
    values = (decision.get("checks") or {}).get(side)
    if not isinstance(values, (list, tuple)) or len(values) != 7:
        return None
    return [bool(x) for x in values]


def leading_side(decision):
    """Choose the better-supported quick side, with RSI as a deterministic tie-break.

    The quick stream is deliberately descriptive even when support is weak; low
    support is reported as weak/high-risk rather than silently suppressing a slot.
    """
    buy_checks = _checks(decision, "BUY")
    sell_checks = _checks(decision, "SELL")
    if buy_checks is None or sell_checks is None:
        return None
    try:
        buy = int(decision.get("buy", sum(buy_checks)))
        sell = int(decision.get("sell", sum(sell_checks)))
    except (TypeError, ValueError):
        buy, sell = sum(buy_checks), sum(sell_checks)
    if buy > sell:
        return "BUY"
    if sell > buy:
        return "SELL"
    try:
        rsi = float(decision.get("rsi"))
    except (TypeError, ValueError):
        rsi = 50.0
    return "BUY" if math.isfinite(rsi) and rsi >= 50.0 else "SELL"


def _opposite_correction(side, correction):
    direction = (correction or {}).get("direction")
    return ((side == "BUY" and direction == "DOWN")
            or (side == "SELL" and direction == "UP"))


def continuation_snapshot(decision, trade, price=None):
    """Describe current rule support for an already-open official V4 paper trade.

    This is a monitoring snapshot, not a new entry signal or calibrated probability.
    It intentionally follows the original trade side even if the current quick bias
    points the other way.
    """
    side = trade.get("side")
    checks = _checks(decision, side)
    if side not in ("BUY", "SELL") or checks is None:
        return None
    score = sum(checks)
    research = decision.get("v4") or {}
    correction = research.get("correction") or {}
    adverse_correction = (
        correction.get("triggered")
        and correction.get("strength") == "STRONG"
        and _opposite_correction(side, correction)
    )
    failed_break = research.get("breakout_state") == "FAILED_BREAK"
    opposite_official = decision.get("side") in ("BUY", "SELL") and decision.get("side") != side

    if opposite_official or adverse_correction or failed_break or score <= 3:
        state = "تحذير"
    elif score >= 6:
        state = "قوية"
    elif score == 5:
        state = "متوسطة"
    else:
        state = "ضعيفة"

    try:
        current_price = float(price if price is not None else decision.get("price"))
    except (TypeError, ValueError):
        current_price = None
    try:
        rsi_value = float(decision.get("rsi"))
    except (TypeError, ValueError):
        rsi_value = None

    return {
        "side": side,
        "state": state,
        "score": score,
        "total": 7,
        "condition_percent": round(score / 7 * 100),
        "conditions": [
            {"name": name, "ok": ok}
            for name, ok in zip(CONDITION_NAMES, checks)
        ],
        "rsi": rsi_value,
        "price": current_price,
        "entry": trade.get("entry"),
        "stop": trade.get("stop"),
        "tp1": trade.get("tp1"),
        "tp2": trade.get("tp2"),
        "tp1_hit": bool(trade.get("tp1_hit")),
        "breakout_state": research.get("breakout_state"),
        "correction_direction": correction.get("direction"),
        "correction_strength": correction.get("strength"),
        "opposite_official": bool(opposite_official),
        "adverse_correction": bool(adverse_correction),
        "failed_break": bool(failed_break),
    }


def _risk_profile(decision, side, score):
    research = decision.get("v4") or {}
    correction = research.get("correction") or {}
    flags = []
    high = False
    medium = False

    if research.get("volatility_regime") == "EXTREME":
        flags.append("تذبذب EXTREME")
        high = True
    elif research.get("volatility_regime") == "HIGH":
        flags.append("تذبذب مرتفع")
        medium = True

    if research.get("breakout_state") == "FAILED_BREAK":
        flags.append("كسر فاشل")
        high = True

    if (correction.get("triggered") and correction.get("strength") == "STRONG"
            and _opposite_correction(side, correction)):
        flags.append("تصحيح قوي عكس الاتجاه")
        high = True

    try:
        buy = int(decision.get("buy", 0))
        sell = int(decision.get("sell", 0))
    except (TypeError, ValueError):
        buy = sell = 0
    if buy == sell:
        flags.append("تعادل الشروط؛ الاتجاه حُسم بالـRSI")
        high = True
    elif abs(buy - sell) == 1:
        flags.append("أفضلية اتجاه محدودة")
        medium = True

    if score <= 3:
        flags.append("تحقق الشروط ضعيف")
        high = True
    elif score <= 5:
        medium = True

    if high:
        return "مرتفعة", flags
    if medium:
        return "متوسطة", flags
    return "منخفضة", flags


def build_quick(decision, now, quote_price=None, lifetime_seconds=1200):
    """Build a quick paper setup for each eligible five-minute observation.

    Unlike the strict official V4 strategy, EXTREME volatility, failed breaks and
    weak rule dominance no longer silence the quick research stream. They are
    surfaced explicitly through the risk label and reasons instead.
    """
    side = leading_side(decision)
    if side is None:
        return None

    checks = _checks(decision, side)
    if checks is None:
        return None
    score = sum(checks)

    research = decision.get("v4") or {}
    try:
        atr = float(decision["atr"])
        price = float(quote_price if quote_price is not None else decision["price"])
        rsi = float(decision.get("rsi"))
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (atr, price, rsi)) or atr <= 0 or price <= 0:
        return None

    risk_level, risk_reasons = _risk_profile(decision, side, score)
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
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
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
    is excluded rather than counted as a win. Unresolved setups expire using the
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


def cancel_quick(original, now, reason="MANUAL_CANCEL"):
    """Retained for explicit/manual research cancellation; official trades do not call it."""
    trade = deepcopy(original)
    if trade.get("status") == "active":
        trade.update(status="closed", outcome=reason, closed=now.timestamp(), r=None)
    return trade
