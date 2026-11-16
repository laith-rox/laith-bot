"""Read-only hourly V4 no-entry advisory policy.

This module does not change trade decisions, entry thresholds, or market guards.
The caller must provide verified latest entry time and a verified market state.
"""
from datetime import datetime, timezone

HOUR_SECONDS = 3600


def should_send_hourly_status(now, last_entry_at, last_notice_at, market_open):
    """Only send once per hour after a verified full hour without entry."""
    if not market_open or last_entry_at is None:
        return False
    now_ts = now.timestamp() if isinstance(now, datetime) else float(now)
    entry_ts = last_entry_at.timestamp() if isinstance(last_entry_at, datetime) else float(last_entry_at)
    if now_ts < entry_ts or now_ts - entry_ts < HOUR_SECONDS:
        return False
    if last_notice_at is not None:
        notice_ts = last_notice_at.timestamp() if isinstance(last_notice_at, datetime) else float(last_notice_at)
        if notice_ts >= entry_ts and now_ts - notice_ts < HOUR_SECONDS:
            return False
    return True


def hourly_status_message(market_state, reason):
    """Describe the actual observed state; never invent volatility or direction."""
    state = str(market_state or "UNKNOWN").upper()
    labels = {
        "HIGH": "تقلبات مرتفعة",
        "EXTREME": "تقلبات شديدة",
        "NORMAL": "تقلبات طبيعية",
        "LOW": "تقلبات منخفضة",
    }
    condition = labels.get(state, "حالة التقلب غير مؤكدة")
    why = str(reason or "لم تتوفر فرصة دخول مؤكدة").strip()
    return (
        "⏳ <b>LAITH V4 | تحديث الساعة — XAUUSD</b>\n"
        f"📊 السوق: {condition}\n"
        f"🔎 سبب الانتظار: {why}\n"
        "🛑 لا توجد إشارة دخول جديدة مؤكدة؛ لا تغامر بدخول عشوائي.\n"
        "👁️ WATCH — مراقبة فقط، والتحليل مستمر."
    )
