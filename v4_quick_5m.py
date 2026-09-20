"""True five-minute decision layer for Laith V4 quick paper setups.

The official V4 strategy remains untouched. This module creates a quick-only
view of the market from CLOSED 5m bars plus a live reference inside the current
5m slot. M15/H1 context is a filter and risk input, not a reason to hide every
quick candidate. Strength describes rule completion, never guaranteed profit.
"""
from copy import deepcopy
import math


QUICK_5M_CONDITION_NAMES = (
    "اتجاه حركة شمعة 5د الحالية",
    "السعر مقابل EMA9 على 5د",
    "اتجاه EMA9/21 على 5د",
    "زخم آخر 3 شموع 5د",
    "اتجاه آخر شمعة 5د مغلقة",
    "موقع السعر من منتصف شمعة 5د السابقة",
    "فلتر الاتجاه الأكبر M15/H1",
)


def _ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    value = float(values[0])
    for item in values[1:]:
        value = alpha * float(item) + (1.0 - alpha) * value
    return value


def _atr(bars, period=14):
    if len(bars) < period + 1:
        return None
    ranges = []
    for previous, bar in zip(bars[-(period + 1):-1], bars[-period:]):
        ranges.append(max(
            float(bar.high) - float(bar.low),
            abs(float(bar.high) - float(previous.close)),
            abs(float(bar.low) - float(previous.close)),
        ))
    value = sum(ranges) / len(ranges)
    return value if math.isfinite(value) and value > 0 else None


def _rsi(closes, period=7):
    if len(closes) < period + 1:
        return None
    changes = [float(b) - float(a) for a, b in zip(closes[-(period + 1):-1], closes[-period:])]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def _safe_score(value):
    try:
        return max(0, min(7, int(value)))
    except (TypeError, ValueError):
        return 0


def _strength(score):
    if score >= 6:
        return "قوية"
    if score == 5:
        return "متوسطة"
    return "ضعيفة"


def analyze_quick_5m(bars, current, higher_decision):
    """Return a quick-only decision driven by 5m evidence.

    A directional candidate is exposed whenever one side leads the other and the
    current-slot movement agrees with that side. Scores below 5/7 are explicitly
    labelled weak instead of being hidden. WAIT is reserved for ties,
    directionless current movement, or unsafe/invalid data.
    """
    decision = deepcopy(higher_decision or {})
    if len(bars or []) < 22 or not isinstance(current, dict):
        decision.update(
            side="WAIT",
            reason="quick_5m_insufficient_data",
            quick_condition_names=list(QUICK_5M_CONDITION_NAMES),
            quick5m={"entry_allowed": False, "side": "WAIT", "reason": "insufficient_data"},
        )
        return decision

    try:
        price = float(current["price"])
        candle_open = float(current["candle_open"])
        candle_high = float(current.get("candle_high", max(price, candle_open)))
        candle_low = float(current.get("candle_low", min(price, candle_open)))
    except (KeyError, TypeError, ValueError):
        decision.update(
            side="WAIT",
            reason="quick_5m_current_candle_invalid",
            quick_condition_names=list(QUICK_5M_CONDITION_NAMES),
            quick5m={"entry_allowed": False, "side": "WAIT", "reason": "current_candle_invalid"},
        )
        return decision

    if not all(math.isfinite(v) and v > 0 for v in (price, candle_open, candle_high, candle_low)):
        decision.update(
            side="WAIT",
            reason="quick_5m_current_candle_invalid",
            quick_condition_names=list(QUICK_5M_CONDITION_NAMES),
            quick5m={"entry_allowed": False, "side": "WAIT", "reason": "current_candle_invalid"},
        )
        return decision

    closes = [float(bar.close) for bar in bars]
    ema9 = _ema(closes, 9)
    ema21 = _ema(closes, 21)
    atr5 = _atr(bars, 14)
    rsi5 = _rsi(closes, 7)
    if None in (ema9, ema21, atr5, rsi5):
        decision.update(
            side="WAIT",
            reason="quick_5m_indicator_unavailable",
            quick_condition_names=list(QUICK_5M_CONDITION_NAMES),
            quick5m={"entry_allowed": False, "side": "WAIT", "reason": "indicator_unavailable"},
        )
        return decision

    previous = bars[-1]
    previous_mid = (float(previous.high) + float(previous.low)) / 2.0
    momentum_anchor = closes[-4]
    higher_buy = _safe_score(decision.get("buy"))
    higher_sell = _safe_score(decision.get("sell"))

    buy_checks = [
        price > candle_open,
        price > ema9,
        ema9 > ema21,
        closes[-1] > momentum_anchor,
        float(previous.close) > float(previous.open),
        price > previous_mid,
        higher_buy >= higher_sell,
    ]
    sell_checks = [
        price < candle_open,
        price < ema9,
        ema9 < ema21,
        closes[-1] < momentum_anchor,
        float(previous.close) < float(previous.open),
        price < previous_mid,
        higher_sell >= higher_buy,
    ]
    buy = sum(buy_checks)
    sell = sum(sell_checks)

    side = "WAIT"
    reason = "quick_5m_wait"
    active_score = 0
    # Current-slot movement is mandatory: if price has not moved away from the
    # slot opening reference, there is no honest fast direction to expose.
    if buy > sell and buy_checks[0]:
        side = "BUY"
        active_score = buy
        reason = "quick_5m_buy_candidate"
    elif sell > buy and sell_checks[0]:
        side = "SELL"
        active_score = sell
        reason = "quick_5m_sell_candidate"

    strength = _strength(active_score) if side in ("BUY", "SELL") else None
    decision.update(
        side=side,
        reason=reason,
        price=price,
        atr=float(atr5),
        rsi=float(rsi5),
        buy=buy,
        sell=sell,
        checks={"BUY": buy_checks, "SELL": sell_checks},
        quick_condition_names=list(QUICK_5M_CONDITION_NAMES),
    )
    decision["quick5m"] = {
        "entry_allowed": side in ("BUY", "SELL"),
        "manual_candidate": side in ("BUY", "SELL"),
        "side": side,
        "reason": reason,
        "buy": buy,
        "sell": sell,
        "strength": strength,
        "rule_completion_percent": round(active_score / 7 * 100) if active_score else 0,
        "calibrated_probability": False,
        "ema9": float(ema9),
        "ema21": float(ema21),
        "atr5": float(atr5),
        "rsi5": float(rsi5),
        "current_open": candle_open,
        "current_price": price,
        "current_high": candle_high,
        "current_low": candle_low,
        "current_open_estimated": bool(current.get("candle_open_estimated")),
        "previous_mid": previous_mid,
        "higher_buy": higher_buy,
        "higher_sell": higher_sell,
        "higher_side": (higher_decision or {}).get("side", "WAIT"),
        "timeframe": "5m",
    }
    return decision


def quick_5m_wait_message(decision, current=None):
    """Compact numbered WAIT card when 5m evidence has no honest direction."""
    q = (decision or {}).get("quick5m") or {}
    if q.get("entry_allowed"):
        return None
    buy = q.get("buy", decision.get("buy", "—") if decision else "—")
    sell = q.get("sell", decision.get("sell", "—") if decision else "—")
    price = q.get("current_price")
    lines = [
        "⏸️ <b>Quick 5د — WAIT</b>",
        f"🔵① الشروط: شراء <b>{buy}/7</b> | بيع <b>{sell}/7</b>",
        "⛔️② الحالة: لا دخول الآن",
        "⛔️③ السبب: الاتجاه اللحظي غير واضح أو البيانات غير كافية؛ لا يتم اختراع صفقة.",
    ]
    if price is not None:
        lines.append(f"🟠④ السعر المرصود: <b>{float(price):.2f}</b>")
    return "\n".join(lines)

