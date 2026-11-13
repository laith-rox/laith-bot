"""Compact Telegram presentation for V4 daily paper-trade counts."""


def daily_report_message(day, counts):
    total = counts["total"]
    return (
        "💎 LAITH V4 | DAILY REPORT\n"
        f"📅 {day.strftime('%d/%m/%Y')} | 🕦 11:30 مساءً\n"
        "━━━━━━━━━━━━\n"
        f"✅ صفقات ناجحة: {total['wins']}\n"
        f"❌ صفقات فاشلة: {total['losses']}\n"
        "━━━━━━━━━━━━\n"
        "📊 صفقات اليوم المغلقة فقط"
    )
