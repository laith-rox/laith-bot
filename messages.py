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
    return (f"🥇 <b>ليث — إشارة {side} XAU/USD</b>\nمستوفية شروط الدخول — غير مضمونة.\n"
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
    watch = store.get("early_watch")
    if watch:
        text += f"🟠 متابعة مبكّرة: <code>{watch['id']}</code> {watch['side']}؛ خارج سجل النتائج\n"
    text += "تقرير اتجاه كل 15د ومتابعة كل 5د خلال ساعات الدخول. لا نسب نجاح مقاسة.\n"
    text += "مراقبة الانعكاس كل 5د عند توفر بيانات سليمة؛ لا إغلاق آلي.\n"
    return text + "/stats النتائج | /pause إيقاف الدخول | /resume استئناف الدخول"


CHECK_LABELS = ["اتجاه 15د", "اتجاه الساعة", "زخم MACD", "نطاق RSI",
                "موضع السعر من المتوسط", "اتجاه شمعة 15د", "عدم ابتعاد السعر عن المتوسط"]


def early(watch, d):
    side = "شراء" if watch["side"] == "BUY" else "بيع"
    move = "صعودًا" if watch["side"] == "BUY" else "نزولًا"
    missing = "، ".join(label for label, ok in zip(CHECK_LABELS, d["checks"][watch["side"]]) if not ok)
    return (f"🟠 <b>ليث — تنبيه {side} مبكّر، غير مضمون</b>\n"
            f"مرجع المتابعة المبكّرة: <code>{watch['id']}</code>\n"
            f"شروط الشراء {d['buy']}/7 | البيع {d['sell']}/7؛ ليست نسب نجاح.\n"
            f"الشروط الناقصة: {escape(missing)}\n"
            f"السعر المرجعي {watch['entry']:.2f}\n"
            f"هدف محتمل أول {watch['tp1']:.2f} — {abs(watch['tp1']-watch['entry']):.2f}$ {move}\n"
            f"هدف محتمل ثانٍ {watch['tp2']:.2f} — {abs(watch['tp2']-watch['entry']):.2f}$ {move}\n"
            f"مستوى إلغاء السيناريو {watch['stop']:.2f} — مسافة {abs(watch['entry']-watch['stop']):.2f}$\n"
            f"وقت الرصد {local_time(watch['created'])} فلسطين.\n"
            "المسافات محسوبة من ATR؛ ليست تنبؤًا بمقدار الحركة أو توقيتها. "
            "الدولار فرق بسعر الأونصة، وليس ربح حسابك.\n"
            "شروط الدخول الكاملة لم تتحقق؛ هذا سيناريو مراقبة. المرجع صالح دقيقتين. "
            "تستمر مراقبته كل 5د حتى بلوغ مستوى الإلغاء/الهدف الثاني أو مرور 4 ساعات، "
            "ويُستبدل عند إرسال إشارة دخول مكتملة. لا يدخل سجل نتائج الصفقات.")


def emergency(watch, d, level, is_early=False):
    opposite = "بيع" if watch["side"] == "BUY" else "شراء"
    cause = (f"اكتملت شروط {opposite} المعاكسة لاتجاه المتابعة."
             if level == "urgent" else
             f"غلبت شروط {opposite} مع زخم وموضع سعر معاكسين على شمعتين مغلقتين متتاليتين.")
    return ("🚨 <b>تحذير انعكاس — راجع الخروج الآن</b>\n"
            + ("متابعة مبكّرة " if is_early else "إشارة ")
            + f"<code>{watch['id']}</code>\n{cause}\n"
            f"شراء {d['buy']}/7 | بيع {d['sell']}/7\n"
            f"آخر سعر مغلق {d['price']:.2f} | {escape(d['price_time'])} UTC\n"
            "إذا دخلت، راجع سعر وسيطك وفكّر بإغلاق الصفقة أو تقليل التعرض. "
            "هذا إنذار تحليلي قد يخطئ، وليس أمر دخول عكسي. "
            "البوت لا يغلق صفقتك ولا ينقل وقفك. المتابعة كل 5د وليست لحظية. "
            "يبقى سجل البوت يتابع المستويات افتراضيًا؛ لا يفترض أنك خرجت.")
