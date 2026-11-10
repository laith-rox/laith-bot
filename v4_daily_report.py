"""Evidence-only V4 daily decision report. Advisory Telegram text; no orders.

Reports decisions observed during a completed Palestine-local day, never a
fabricated trade P/L or win rate. Suppresses empty reports and future records.
"""
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo
from v4_decision_journal import journal_summary

LOCAL_TZ = ZoneInfo("Asia/Hebron")


def plan_daily_decision_report(now, events, *, earliest_local_hour=7):
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = now.astimezone(LOCAL_TZ)
    if local.hour < earliest_local_hour:
        return None
    previous = local.date() - timedelta(days=1)
    selected = []
    for item in events if isinstance(events, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            observed = datetime.fromisoformat(item["observed_at"].replace("Z", "+00:00"))
            if observed.tzinfo is None or observed.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                continue
            if observed.astimezone(LOCAL_TZ).date() == previous:
                selected.append(item)
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    if not selected:
        return None
    summary = journal_summary(selected)
    counts = summary["states"]
    top = list(summary["block_reasons"].items())[:3]
    blockers = "، ".join(f"{escape(reason, quote=True)}: {count}" for reason, count in top) or "لا يوجد"
    return {"key": f"v4_daily_decisions:{previous.isoformat()}",
            "message": (
                f"📊 <b>Laith V4 — تقرير القرارات {previous.isoformat()}</b>\\n"
                f"إجمالي القرارات المسجلة: {summary['decision_count']}\\n"
                f"جاهزة: {counts['READY']} | انتظار: {counts['WAIT']} | "
                f"مرفوضة: {counts['REJECTED']} | ملغاة: {counts['INVALID']}\\n"
                f"أكثر أسباب المنع: {blockers}\\n"
                "⚠️ هذا إحصاء قرارات فقط، وليس نتائج صفقات أو نسبة نجاح. "
                "الإشارات للتنفيذ اليدوي فقط."
            ).replace('\\\\n', '\\n')}
