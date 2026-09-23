"""Safety guard for Laith V4 quick paper signals only.

Quick candidates remain visible when weak/high-risk, but correlated exposure is capped:\nonly one active quick per direction and at most two active quicks total. The stop-streak\ncooldown remains active after repeated losses.
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
    """Cap correlated exposure, then apply the same-side stop-streak cooldown."""
    side = setup.get("side")
    active = [trade for trade in (trades or []) if trade.get("status") in ("active", "uncertain_delivery")]
    same_side = [trade for trade in active if trade.get("side") == side]
    if same_side:
        return {
            "allowed": False,
            "reason": "same_side_exposure",
            "side": side,
            "detail": "يوجد بالفعل Quick مفتوحة بنفس الاتجاه",
            "active_count": len(active),
        }
    if len(active) >= 2:
        return {
            "allowed": False,
            "reason": "max_quick_exposure",
            "side": side,
            "detail": "تم بلوغ حد صفقتين Quick مفتوحتين",
            "active_count": len(active),
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
        "بعد ستوبين متتاليين بنفس الاتجاه يتوقف إرسال صفقة جديدة مؤقتًا. "
        "هذا لا يغيّر مسار صفقة الربع ساعة."
    )
