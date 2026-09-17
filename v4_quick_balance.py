"""Condition-balance, correction and intelligence display helpers for Laith V4 quick paper signals."""

from v4_intelligence import enhance_quick_message
from v4_telegram import quick_message as _base_quick_message


def _score(decision, side):
    checks = (decision.get("checks") or {}).get(side)
    fallback = sum(bool(x) for x in checks) if isinstance(checks, (list, tuple)) else 0
    try:
        value = int(decision.get(side.lower(), fallback))
    except (TypeError, ValueError):
        value = fallback
    return max(0, min(7, value))


def _fmt_price(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _direction_ar(direction):
    return {"DOWN": "نزول", "UP": "صعود"}.get(str(direction or "").upper(), "غير متاح")


def _strength_ar(strength):
    return {
        "STRONG": "قوية",
        "MEDIUM": "متوسطة",
        "WEAK": "ضعيفة",
        "UNAVAILABLE": "غير متاحة",
    }.get(str(strength or "").upper(), str(strength or "غير متاحة"))


def strength_marker(strength):
    """Telegram has no portable text-color API, so use stable color markers."""
    return {
        "قوية": "🟢",
        "متوسطة": "🟡",
        "ضعيفة": "🔴",
        "تحذير": "🚨",
    }.get(str(strength or ""), "⚪")


def attach_condition_balance(setup, decision):
    """Attach both rule counts, correction map and V4 intelligence to a quick setup."""
    if setup is None:
        return None
    buy_score = _score(decision, "BUY")
    sell_score = _score(decision, "SELL")
    research = decision.get("v4") or {}
    correction = research.get("correction") or {}
    setup.update(
        buy_score=buy_score,
        sell_score=sell_score,
        buy_percent=round(buy_score / 7 * 100),
        sell_percent=round(sell_score / 7 * 100),
        correction_direction=correction.get("direction"),
        correction_strength=correction.get("strength"),
        correction_triggered=bool(correction.get("triggered")),
        correction_target1=correction.get("target1"),
        correction_target2=correction.get("target2"),
        correction_invalidation=correction.get("invalidation"),
        correction_start_zone=correction.get("start_zone"),
        intelligence=research.get("intelligence") or {},
    )
    return setup


def condition_balance_line(trade):
    """Show the active trade side first and the opposite side in parentheses."""
    side = trade.get("side")
    try:
        buy_score = int(trade.get("buy_score"))
        sell_score = int(trade.get("sell_score"))
    except (TypeError, ValueError):
        return None
    buy_percent = trade.get("buy_percent", round(buy_score / 7 * 100))
    sell_percent = trade.get("sell_percent", round(sell_score / 7 * 100))
    if side == "SELL":
        return (
            f"📊 شروط البيع: <b>{sell_score}/7 = {sell_percent}%</b> "
            f"(شروط الشراء: {buy_score}/7 = {buy_percent}%)"
        )
    if side == "BUY":
        return (
            f"📊 شروط الشراء: <b>{buy_score}/7 = {buy_percent}%</b> "
            f"(شروط البيع: {sell_score}/7 = {sell_percent}%)"
        )
    return None


def correction_block(trade):
    """Format the already-computed V4 correction map as an explanatory display block."""
    direction = trade.get("correction_direction")
    target1 = trade.get("correction_target1")
    target2 = trade.get("correction_target2")
    if not direction or (target1 is None and target2 is None):
        return []
    state = "مُفعّل" if trade.get("correction_triggered") else "مراقبة"
    lines = [
        f"↩️ توقع التصحيح: <b>{_direction_ar(direction)}</b> | القوة: {_strength_ar(trade.get('correction_strength'))} | الحالة: {state}",
        f"🎯 نطاق التصحيح المتوقع: الأقرب {_fmt_price(target1)} | الأعمق {_fmt_price(target2)}",
    ]
    invalidation = trade.get("correction_invalidation")
    if invalidation is not None:
        lines.append(f"🚫 إبطال توقع التصحيح: {_fmt_price(invalidation)}")
    return lines


def quick_message(trade):
    """Reuse the standard message and add balance, correction and smart V4 context."""
    message = _base_quick_message(trade)
    lines = message.splitlines()
    balance = condition_balance_line(trade)
    if balance:
        for index, line in enumerate(lines):
            if line.startswith("📊 تحقق الشروط:"):
                lines[index] = balance
                break

    marker = strength_marker(trade.get("strength"))
    for index, line in enumerate(lines):
        if line.startswith("🧭 القوة المعروضة:"):
            lines[index] = f"{marker} القوة المعروضة: <b>{trade.get('strength', '—')}</b>"
            break

    correction = correction_block(trade)
    if correction:
        insert_at = None
        for index, line in enumerate(lines):
            if line.startswith("🎯 الهدف السريع:"):
                insert_at = index + 1
                break
        if insert_at is None:
            insert_at = len(lines)
        lines[insert_at:insert_at] = correction
    return enhance_quick_message("\n".join(lines), trade)
