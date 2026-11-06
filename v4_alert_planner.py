"""Pure alert dispatch guards for V4; no broker orders and no network calls."""
from v4_market_guard import close_alert_key
from v4_news_intelligence import plan_pre_news_alert


def plan_market_close_notice(now, intervals, last_quote_at, *, weekly=False,
                             already_sent_keys=()):
    """Build one T-30 close warning when verified schedule and quote permit."""
    # Calendar-based close warnings must not disappear when quote data is stale.
    # Quote freshness is independently required for trade ENTRY signals.
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    from datetime import timezone
    now_utc = now.astimezone(timezone.utc)
    candidates = []
    for opened, closes in intervals:
        if opened.tzinfo is None or closes.tzinfo is None or opened >= closes:
            continue
        opened = opened.astimezone(timezone.utc)
        closes = closes.astimezone(timezone.utc)
        if opened <= now_utc < closes:
            until = (closes - now_utc).total_seconds()
            if 29 * 60 <= until <= 30 * 60:
                candidates.append(closes)
    if not candidates:
        return None
    closes = min(candidates)
    key = close_alert_key(closes, weekly=weekly)
    if key in already_sent_keys:
        return None
    scope = "الأسبوعي" if weekly else "اليومي"
    return {"key": key, "message": (
        "⏰ <b>Laith V4 — تنبيه الإغلاق %s</b>\n"
        "باقي نحو 30 دقيقة على إغلاق سوق الذهب حسب جدول الوسيط.\n"
        "⛔ توقفت إشارات الدخول الجديدة حتى إعادة فتح السوق والتحقق من الأسعار.\n"
        "📌 هذا تنبيه فقط؛ لا يغلق صفقاتك على MT5."
    ) % scope}


def plan_verified_news_notices(now, events, *, already_sent_keys=()):
    """Generate distinct T-20 news notices from independently verified events."""
    notices = []
    for event in events:
        notice = plan_pre_news_alert(now, event)
        if notice and notice["key"] not in already_sent_keys:
            notices.append(notice)
    return notices
