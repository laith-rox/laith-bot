"""Session-aware manual Telegram entry lifecycle for Laith V4.

This is a pure state machine. Live quote and broker session verification must
be supplied by adapters; it never sends orders or assumes market hours.
"""
from v4_signal_dedupe import signal_identity, should_publish_signal, mark_signal_published


def plan_entry_notification(store, candidate, *, session_id, market_state,
                            quote_verified, news_safe):
    """Build an actionable notification only when every safety guard is green."""
    if market_state != "OPEN":
        return None
    if not quote_verified or not news_safe:
        return None
    if not should_publish_signal(store, candidate, session_id=session_id):
        return None
    side = candidate["side"]
    label = "شراء BUY" if side == "BUY" else "بيع SELL"
    horizon = candidate.get("horizon") or "SCALP"
    entry, stop, target = (float(candidate[key]) for key in ("entry", "stop", "target"))
    message = (
        "🟢 <b>Laith V4 — دخول يدوي مؤكد</b>\n"
        "الاتجاه: <b>%s</b> | النوع: %s\n"
        "الدخول المرجعي: %.2f\n"
        "وقف الخسارة: %.2f\n"
        "الهدف: %.2f\n"
        "⚠️ راجع السعر الحالي والسبريد قبل التنفيذ؛ لا يوجد تنفيذ تلقائي."
    ) % (label, horizon, entry, stop, target)
    return {"message": message, "identity": signal_identity(candidate),
            "session_id": session_id, "candidate": candidate}


def publish_entry_notification(store, notifier, planned):
    """Mark as sent only after Telegram reports delivery success."""
    if not planned:
        return False
    if not should_publish_signal(store, planned["candidate"], session_id=planned["session_id"]):
        return False
    if notifier.send(planned["message"]) is not True:
        return False
    mark_signal_published(store, planned["candidate"], session_id=planned["session_id"])
    return True
