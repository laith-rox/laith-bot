from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("Asia/Hebron")

REASONS = {
    "conditions_not_aligned": "شروط الدخول غير متوافقة",
    "entry_conditions_met": "شروط الدخول تحققت",
    "price_extended": "السعر بعيد عن متوسطه؛ انتظار فرصة أقرب",
    "rsi_extreme": "تشبّع في الزخم؛ انتظار اعتداله",
    "recent_data_gap": "نقص في الشموع الأخيرة",
    "calendar_unavailable": "تعذّر تأكيد حداثة جدول الأخبار",
    "news_blackout": "فترة حماية حول خبر أمريكي عالي التأثير",
    "outside_entry_window": "خارج ساعات إرسال إشارات جديدة",
    "active_signal": "إشارة سابقة قيد المتابعة",
    "cooldown": "مهلة بين الإشارات",
    "paused": "إرسال الإشارات الجديدة متوقف",
    "daily_risk_limit": "بلوغ حد الخسارة اليومي لنموذج الإشارات",
    "already_evaluated": "بانتظار إغلاق شمعة 15 دقيقة جديدة",
    "market_closed_candles_stale": "بيانات الأسعار متأخرة",
    "market_insufficient_closed_history": "بيانات تاريخية غير كافية للتحليل",
    "market_quota_reached": "نفدت حصة مصدر الأسعار مؤقتًا",
    "market_connection_failed": "تعذّر الاتصال بمصدر الأسعار",
    "delivery_uncertain": "تعذّر التأكد من وصول رسالة؛ راجع الإشارة قبل /resume",
}


def local_time(value):
    return datetime.fromtimestamp(value, LOCAL).strftime("%d/%m %H:%M")


def entry(trade, decision):
    side = "شراء 🟢" if trade["side"] == "BUY" else "بيع 🔴"
    passed = decision["buy"] if trade["side"] == "BUY" else decision["sell"]
    return (f"🥇 <b>ليث — إشارة {side} XAU/USD</b>\n"
            f"مرجع الإشارة: <code>{trade['id']}</code>\n"
            f"السعر المرجعي: <b>{trade['entry']:.2f}</b>\n"
            f"الوقف المقترح: <b>{trade['stop']:.2f}</b>\n"
            f"الهدف الأول: <b>{trade['tp1']:.2f}</b>\n"
            f"الهدف الثاني: <b>{trade['tp2']:.2f}</b>\n"
            f"تحقق {passed}/7 شروط مع حماية التشبّع ومطاردة السعر.\n"
            f"الوقت: {local_time(trade['created'])} فلسطين.\n"
            "السعر من آخر شمعة 5د مغلقة؛ صلاحية اقتراح الدخول دقيقتان. "
            "إذا ابتعد السعر، انتظر فرصة جديدة.\n"
            "تنبيه تحليلي؛ فتح الصفقة ووضع الوقف يتمان عند وسيطك. "
            "المتابعة كل 5د، والوصول للهدف الأول يولّد اقتراح حماية عند الدخول. "
            "عدد الشروط ليس احتمال نجاح.")


def transition(trade, kind):
    prefix = f"🥇 <b>متابعة إشارة ليث</b> — <code>{trade['id']}</code>\n"
    if kind == "tp1":
        return (prefix + f"رُصد وصول السعر للهدف الأول {trade['tp1']:.2f}.\n"
                f"اقتراح: نقل الوقف إلى سعر الدخول {trade['entry']:.2f} إذا سمح سعر وسيطك الحالي.\n"
                "نموذج المتابعة يفعّل مستوى الحماية من الشمعة التالية. "
                "البوت لا يغيّر أمر الوقف عند الوسيط، والرسوم قد تجعل الإغلاق عند الدخول خاسرًا.")
    label = {"TP2": "رُصد الهدف الثاني", "STOP": "رُصد مستوى الوقف",
             "PROTECTED_STOP": "رُصد مستوى الحماية بعد الهدف الأول",
             "AMBIGUOUS": "الشمعة لمست الوقف والهدف وترتيب اللمسات غير محسوم"}[trade["outcome"]]
    result = prefix + label + f".\nوقت الرصد: {local_time(trade['closed'])}.\n"
    if trade.get("r") is None:
        result += "النتيجة مستبعدة من إحصاءات الربح لوجود غموض أو فجوة بيانات/تأكيد إرسال."
    else:
        result += f"نتيجة نموذج المتابعة: {trade['r']:+.2f}R قبل السبريد والرسوم؛ ليست ربح حسابك بالدولار."
    return result


def stats(store):
    s = store.stats()
    return ("📊 <b>سجل إشارات ليث</b>\n"
            f"انتهت متابعتها: {s['closed']} | قابلة للقياس: {s['measured']}\n"
            f"موجبة: {s['wins']} | سالبة: {s['losses']} | عند الدخول: {s['flat']}\n"
            f"غير محسومة/مستبعدة: {s['unresolved']}\n"
            f"المحصلة: {s['total_r']:+.2f}R | أكبر تراجع: {s['drawdown_r']:.2f}R\n"
            "R هي المسافة بين الدخول والوقف الأول. هذه متابعة افتراضية للأسعار، "
            "بلا احتساب سبريد وسيطك أو رسومه، وبلا تأكيد أنك نفّذت الصفقة.")


def status(store):
    last = store.get("last_analysis", {})
    active = store.active()
    reason = store.get("last_error") or last.get("reason", "بانتظار أول تحليل")
    state = "متوقف عن إشارات جديدة" if store.get("paused", False) else "مراقبة مفعّلة"
    text = f"🥇 <b>بوت ليث</b>\n{state}\n{escape(REASONS.get(reason, reason))}\n"
    seen = store.get("last_market_ok")
    if seen:
        text += f"آخر بيانات ناجحة: {local_time(seen)} فلسطين\n"
    if active:
        text += (f"الإشارة الحالية: <code>{active['id']}</code> {active['side']}\n"
                 f"المرجع {active['entry']:.2f} | الوقف {active['stop']:.2f}\n")
        if active["delivery_uncertain"]:
            text += "⚠️ وصول رسالة الدخول غير مؤكد؛ التحقق مطلوب قبل استئناف إشارات جديدة.\n"
    return text + "/stats النتائج | /pause إيقاف الدخول | /resume استئناف الدخول"
