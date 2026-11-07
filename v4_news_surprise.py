"""Verified post-release economic surprise analysis for manual V4 alerts.

No release prediction, no automatic orders, no unverified gold-direction claim.
Requires a provider-verified actual, comparable numeric consensus, and a
source timestamp after the scheduled release and not in the future.
"""
from datetime import datetime, timezone, timedelta
import math


def _number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing numeric value")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value.endswith("%"):
            value = value[:-1].strip()
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite")
    return result


def plan_post_news_alert(now, event, *, max_delay_minutes=30):
    if not isinstance(now, datetime) or now.tzinfo is None or not isinstance(event, dict):
        return None
    at = event.get("release_at")
    published = event.get("actual_published_at")
    if not isinstance(at, datetime) or at.tzinfo is None or not isinstance(published, datetime) or published.tzinfo is None:
        return None
    now, at, published = (t.astimezone(timezone.utc) for t in (now, at, published))
    if (event.get("calendar_verified") is not True or
            event.get("actual_verified") is not True or
            event.get("importance") != "high" or not event.get("id") or
            not isinstance(event.get("actual_source"), str) or not event["actual_source"].strip() or
            not at <= published <= now <= at + timedelta(minutes=max_delay_minutes)):
        return None
    try:
        actual = _number(event.get("actual"))
        consensus = _number(event.get("consensus"))
    except (ValueError, TypeError):
        return None
    surprise = actual - consensus
    direction = "أعلى من المتوقع" if surprise > 0 else "أقل من المتوقع" if surprise < 0 else "مطابق للتوقع"
    title = str(event.get("title") or "خبر اقتصادي").replace("<", "&lt;").replace(">", "&gt;")
    source = event["actual_source"].strip().replace("<", "&lt;").replace(">", "&gt;")
    key = "v4_news_actual:%s:%s:%s" % (event["id"], at.isoformat(), published.isoformat())
    return {"key": key, "event_id": event["id"], "message": (
        "📰 <b>Laith V4 — نتيجة خبر مؤكدة</b>\n"
        f"الخبر: {title}\n"
        f"الفعلي: {actual:g} | المتوقع: {consensus:g}\n"
        f"المفاجأة العددية: {surprise:+g} ({direction})\n"
        f"المصدر: {source}\n"
        "⚠️ لا نستنتج اتجاه الذهب من الرقم وحده؛ ننتظر حركة سعر حية وتأكيدًا مستقلًا. "
        "إشارات يدوية فقط، دون تنفيذ أوامر.")}
