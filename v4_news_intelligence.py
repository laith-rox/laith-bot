"""V4 high-impact economic news alert planner (manual Telegram only).

Upstream must supply verified calendar events and consensus. No invented forecast.
"""
from datetime import timedelta, timezone
from html import escape


def plan_pre_news_alert(now, event, *, lead_minutes=20, tolerance_seconds=60):
    """Return an alert payload only inside the T-20 minute window.

    Caller must persist alert_key after successful Telegram delivery to dedupe.
    """
    at = event.get("release_at")
    event_id = event.get("id")
    if not at or not at.tzinfo or not now.tzinfo or not event_id:
        return None
    at = at.astimezone(timezone.utc)
    now = now.astimezone(timezone.utc)
    seconds = (at - now - timedelta(minutes=lead_minutes)).total_seconds()
    if not 0 <= seconds < tolerance_seconds:
        return None
    if event.get("importance") != "high":
        return None
    if event.get("calendar_verified") is not True:
        return None
    title = event.get("title") or "حدث اقتصادي"
    consensus = event.get("consensus")
    previous = event.get("previous")
    expectation = event.get("conditional_scenario") or "غير متاح — لا توقع موثوق"
    risk = event.get("risk") or "مرتفعة"
    key = "v4_news_20m:%s:%s" % (event_id, at.isoformat())
    message = (
        "🚨 <b>V4 — خبر مهم بعد 20 دقيقة</b>\n"
        "📅 %s — %s UTC\n"
        "📊 المتوقع: %s | السابق: %s\n"
        "🧠 سيناريو مشروط: %s\n"
        "⚠️ مخاطرة الذهب: %s\n"
        "⛔ لا دخول على الخبر وحده؛ ننتظر النتيجة وتأكيد السعر."
    ) % (escape(str(title)), at.strftime("%Y-%m-%d %H:%M"),
         escape(str("غير متاح" if consensus is None else consensus)),
         escape(str("غير متاح" if previous is None else previous)),
         escape(str(expectation)), escape(str(risk)))
    return {"key": key, "message": message, "event_id": event_id}
