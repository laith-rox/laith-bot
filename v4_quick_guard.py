"""Safety guard for Laith V4 quick paper signals only.

The official V4 strategy is untouched. This module filters only the five-minute
quick paper stream after a setup has already been built.
"""

STOP_STREAK_LIMIT = 2
STOP_COOLDOWN_SECONDS = 15 * 60


def _closed_time(trade):
    try:
        return float(trade.get("closed"))
    except (TypeError, ValueError):
        return 0.0


def _stop_streak(trades, side):
    closed = [
        trade for trade in (trades or [])
        if trade.get("status") == "closed" and trade.get("side") == side and _closed_time(trade) > 0
    ]
    closed.sort(key=_closed_time)
    streak = 0
    last_stop_time = 0.0
    for trade in reversed(closed):
        if trade.get("outcome") != "STOP":
            break
        streak += 1
        if not last_stop_time:
            last_stop_time = _closed_time(trade)
    return streak, last_stop_time


def guard_quick_setup(setup, trades, now):
    """Return whether a quick setup may be emitted under the approved guard rules."""
    side = setup.get("side")
    try:
        score = int(setup.get("score", 0))
    except (TypeError, ValueError):
        score = 0

    if score <= 4 and setup.get("risk_level") == "مرتفعة":
        return {
            "allowed": False,
            "reason": "weak_high_risk",
            "side": side,
            "detail": "صفقة ضعيفة 4/7 أو أقل مع مخاطرة مرتفعة",
        }

    same_side_active = [
        trade for trade in (trades or [])
        if trade.get("status") == "active" and trade.get("side") == side
    ]
    if same_side_active:
        return {
            "allowed": False,
            "reason": "same_side_active",
            "side": side,
            "detail": "توجد صفقة سريعة قائمة بالفعل بنفس الاتجاه",
            "active_count": len(same_side_active),
        }

    streak, last_stop_time = _stop_streak(trades, side)
    if streak >= STOP_STREAK_LIMIT and last_stop_time:
        cooldown_until = last_stop_time + STOP_COOLDOWN_SECONDS
        now_ts = now.timestamp()
        if now_ts < cooldown_until:
            remaining = max(0, int(cooldown_until - now_ts))
            return {
                "allowed": False,
                "reason": "stop_cooldown",
                "side": side,
                "detail": f"{streak} ستوبات متتالية بنفس الاتجاه",
                "stop_streak": streak,
                "cooldown_until": cooldown_until,
                "remaining_seconds": remaining,
                "fingerprint": f"{side}:{int(last_stop_time)}:{int(cooldown_until)}",
            }

    return {"allowed": True, "reason": None, "side": side}


def guard_alert_message(block):
    """One-shot emergency warning used when a stop-streak cooldown is active."""
    side_ar = "شراء" if block.get("side") == "BUY" else "بيع"
    seconds = int(block.get("remaining_seconds", 0) or 0)
    minutes = max(1, (seconds + 59) // 60)
    return (
        "🚨 <b>طوارئ V4 — إيقاف مؤقت للسريع</b>\n\n"
        f"الاتجاه: <b>{side_ar}</b>\n"
        f"السبب: {block.get('detail', 'ستوبات متتالية')}\n"
        f"⏳ المهلة المتبقية: حوالي <b>{minutes} دقيقة</b>\n\n"
        "لن تُفتح صفقة سريعة جديدة بنفس الاتجاه أثناء المهلة. "
        "الصفقات الرسمية V4 وشروطها والستوب والأهداف لم تتغير."
    )
