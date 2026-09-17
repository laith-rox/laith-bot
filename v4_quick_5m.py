"""True five-minute decision layer for Laith V4 quick paper setups.

The official V4 strategy remains untouched.  This module creates a quick-only
view of the market from CLOSED 5m bars plus the provider's currently-forming 5m
candle.  M15/H1 context is used only as a higher-timeframe filter.
"""
from copy import deepcopy
import math


QUICK_5M_CONDITION_NAMES = (
    "اتجاه شمعة 5د الحالية",
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


def analyze_quick_5m(bars, current, higher_decision):
    """Return a quick-only decision driven by 5m evidence.

    Entry requires at least 5/7 checks, a two-check advantage over the opposite
    side, agreement from the current 5m candle direction, and no conflict with
    the M15/H1 filter.  A non-qualified slot becomes WAIT rather than forcing a
    trade.  Scores describe rule completion, not probability of profit.
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
    if buy >= 5 and buy - sell >= 2 and buy_checks[0] and buy_checks[6]:
        side = "BUY"
        reason = "quick_5m_buy_confirmed"
    elif sell >= 5 and sell - buy >= 2 and sell_checks[0] and sell_checks[6]:
        side = "SELL"
        reason = "quick_5m_sell_confirmed"

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
        "side": side,
        "reason": reason,
        "buy": buy,
        "sell": sell,
        "ema9": float(ema9),
        "ema21": float(ema21),
        "atr5": float(atr5),
        "rsi5": float(rsi5),
        "current_open": candle_open,
        "current_price": price,
        "current_high": candle_high,
        "current_low": candle_low,
        "previous_mid": previous_mid,
        "higher_buy": higher_buy,
        "higher_sell": higher_sell,
        "higher_side": (higher_decision or {}).get("side", "WAIT"),
        "timeframe": "5m",
    }
    return decision


def quick_5m_wait_message(decision, current=None):
    """Compact Telegram WAIT message for an aligned 5m slot with weak/mixed evidence."""
    q = (decision or {}).get("quick5m") or {}
    if q.get("entry_allowed"):
        return None
    buy = q.get("buy", decision.get("buy", "—") if decision else "—")
    sell = q.get("sell", decision.get("sell", "—") if decision else "—")
    price = q.get("current_price")
    start = (current or {}).get("candle_start_iso") if isinstance(current, dict) else None
    lines = [
        "⏸️ <b>Quick 5د — WAIT</b>",
        "",
        f"📊 شراء: <b>{buy}/7</b> | بيع: <b>{sell}/7</b>",
        "السبب: شروط شمعة 5د الحالية غير كافية أو متعارضة؛ لا يتم إجبار صفقة.",
    ]
    if price is not None:
        lines.append(f"💰 السعر المرصود: <b>{float(price):.2f}</b>")
    if start:
        lines.append(f"🕯️ شمعة المصدر: {start}")
    lines.append("⚠️ هذه قراءة قواعد وليست احتمال ربح.")
    return "\n".join(lines)
