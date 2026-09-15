from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("Asia/Hebron")

REASONS = {
    "context_conflict": "تعارض حركة القمم والقيعان القصيرة مع اتجاه الساعة؛ لا دخول",
    "context_pullback": "تصحيح محتمل؛ انتظار تأكيد عودة الاتجاه",
    "context_trend_break": "كسر نطاق الاتجاه؛ انتظار تأكيد اتجاه جديد",
    "context_unclear": "اتجاه غير محسوم أو فجوة بيانات؛ انتظار",
    "conditions_not_aligned": "شروط الدخول غير متوافقة",
    "entry_conditions_met": "شروط الدخول تحققت",
    "best_available_bias": "ترجيح أولي؛ شروط الدخول الكاملة غير متحققة",
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


def price_time(decision):
    try:
        stamp = datetime.fromisoformat(decision['price_time'])
        if stamp.tzinfo is None:
            return 'غير متاح'
        return stamp.astimezone(LOCAL).strftime('%d/%m %H:%M')
    except (KeyError, TypeError, ValueError):
        return 'غير متاح'


def fully_qualified(decision, side):
    checks = decision.get('checks', {}).get(side, [])
    return (decision.get('side') == side and not decision.get('forced', False)
            and decision.get('reason') != 'best_available_bias'
            and len(checks) == 7 and sum(checks) >= 6
            and all(checks[i] for i in (0, 1, 3, 4, 6)))


def entry(trade, decision):
    side = "🟢 شراء" if trade["side"] == "BUY" else "🔴 بيع"
    passed = decision["buy"] if trade["side"] == "BUY" else decision["sell"]
    grade = ('مستوفية شروط الدخول — غير مضمونة' if fully_qualified(decision, trade['side'])
             else 'ترجيح أولي — غير مضمون، خطر مرتفع')
    return (f"<b>{side} | إشارة ذهب جديدة</b>\n"
            f"المرجع: <code>{escape(trade['id'])}</code>\n{grade}\n\n"
            f"الدخول المرجعي: <b>{trade['entry']:.2f}</b>\n"
            f"الوقف المقترح: <b>{trade['stop']:.2f}</b>\n"
            f"هدف 1: <b>{trade['tp1']:.2f}</b>\n"
            f"هدف 2: <b>{trade['tp2']:.2f}</b>\n\n"
            f"الشروط المتحققة: {passed}/7؛ ليست نسبة نجاح.\n"
            f"آخر إغلاق 5د: {price_time(decision)} فلسطين\n"
            f"وقت الإشارة: {local_time(trade['created'])} فلسطين\n\n"
            "صلاحية اقتراح الدخول دقيقتان؛ افحص السعر الحالي عند وسيطك.\n"
            "التحديث كل 5د كردّ على هذه الرسالة. التنفيذ والوقف عند وسيطك.")


def transition(trade, kind):
    side = 'شراء' if trade['side'] == 'BUY' else 'بيع'
    reference = f"{side} | المرجع: <code>{escape(trade['id'])}</code>\n"
    if kind == "tp1":
        return ("🎯 <b>رُصد الهدف الأول</b>\n" + reference +
                f"\nالهدف الأول: <b>{trade['tp1']:.2f}</b>\n"
                f"الهدف التالي: <b>{trade['tp2']:.2f}</b>\n"
                f"الحماية المقترحة: <b>{trade['entry']:.2f}</b> عند الدخول\n\n"
                "راجع نقل الوقف إذا سمح سعر وسيطك؛ البوت لا ينقله تلقائيًا.\n"
                "الحماية في النموذج تبدأ من الشمعة التالية؛ الرسوم قد تجعلها خاسرة.")
    label = {"TP2": "رُصد الهدف الثاني", "STOP": "رُصد مستوى الوقف",
             "PROTECTED_STOP": "رُصد مستوى الحماية بعد الهدف الأول",
             "AMBIGUOUS": "الشمعة لمست الوقف والهدف وترتيب اللمسات غير محسوم"}[trade["outcome"]]
    result = "🏁 <b>انتهت متابعة الإشارة</b>\n" + reference + '\n' + label + '.\n'
    if trade.get('exit') is not None:
        result += f"سعر نهاية المتابعة: <b>{trade['exit']:.2f}</b>\n"
    result += f"وقت الرصد: {local_time(trade['closed'])} فلسطين\n\n"
    if trade.get("r") is None:
        result += "النتيجة مستبعدة من إحصاءات الربح لوجود غموض أو فجوة بيانات/تأكيد إرسال."
    else:
        result += f"نتيجة نموذج المتابعة: {trade['r']:+.2f}R قبل السبريد والرسوم؛ ليست ربح حسابك بالدولار."
    return result + '\nهذا إغلاق في نموذج المتابعة؛ البوت لا يغلق صفقتك عند الوسيط.'


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
    text += "متابعة الإشارة الحالية كل 5د؛ وعند عدم وجود إشارة، تقرير سوق كل 15د وتحديث كل 5د. لا نسب نجاح مقاسة.\n"
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
    cause = ((f"اكتملت شروط {opposite} المعاكسة لاتجاه المتابعة."
              if fully_qualified(d, 'SELL' if watch['side'] == 'BUY' else 'BUY') else
              f"تحوّل ترجيح النموذج إلى {opposite}؛ شروطه الكاملة غير متحققة.")
             if level == "urgent" else
             f"غلبت شروط {opposite} مع زخم وموضع سعر معاكسين على شمعتين مغلقتين متتاليتين.")
    if level == "structure":
        cause = "كُسر نطاق سابق عكس اتجاه المتابعة بإغلاقين 15د؛ لم نعد نصنّف الحركة كتراجع تصحيحي فقط."
    title = '🚨 تحذير انعكاس — راجع الخروج' if level != 'pressure' else '⚠️ ضغط عكسي — راجع المخاطر'
    if level == 'pressure':
        cause = 'القمم والقيعان القصيرة تتحرك عكس الإشارة؛ انعكاس الاتجاه غير محسوم.'
    side = 'شراء' if watch['side'] == 'BUY' else 'بيع'
    scope = 'السيناريو المبكّر' if is_early else 'الإشارة'
    return (f"<b>{title}</b>\n{scope}: {side} | <code>{escape(watch['id'])}</code>\n\n"
            f"{cause}\n"
            f"آخر إغلاق 5د: <b>{d['price']:.2f}</b>\n"
            f"وقت السعر: {price_time(d)} فلسطين\n\n"
            "إذا دخلت، راجع تقليل التعرض أو الخروج بسعر وسيطك الحالي.\n"
            "تحذير قد يخطئ؛ ليس دخولًا عكسيًا ولا إغلاقًا آليًا.\n"
            "المتابعة مستمرة كل 5د؛ لا تنتظر الرسائل لتنفيذ وقفك.")
