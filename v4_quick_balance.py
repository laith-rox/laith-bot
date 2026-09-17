"""Condition-balance display helpers for Laith V4 quick paper signals."""

from v4_telegram import quick_message as _base_quick_message


def _score(decision, side):
    checks = (decision.get("checks") or {}).get(side)
    fallback = sum(bool(x) for x in checks) if isinstance(checks, (list, tuple)) else 0
    try:
        value = int(decision.get(side.lower(), fallback))
    except (TypeError, ValueError):
        value = fallback
    return max(0, min(7, value))


def attach_condition_balance(setup, decision):
    """Attach both BUY and SELL rule counts to a quick setup without changing entry logic."""
    if setup is None:
        return None
    buy_score = _score(decision, "BUY")
    sell_score = _score(decision, "SELL")
    setup.update(
        buy_score=buy_score,
        sell_score=sell_score,
        buy_percent=round(buy_score / 7 * 100),
        sell_percent=round(sell_score / 7 * 100),
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


def quick_message(trade):
    """Reuse the standard V4 message, replacing only the one-sided condition-count line."""
    message = _base_quick_message(trade)
    balance = condition_balance_line(trade)
    if not balance:
        return message
    lines = message.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("📊 تحقق الشروط:"):
            lines[index] = balance
            break
    return "\n".join(lines)
