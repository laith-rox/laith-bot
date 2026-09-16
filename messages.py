from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("Asia/Hebron")

REASONS = {
    "market_quote_invalid": "تعذّر التحقق من سعر حديث ومؤرّخ؛ لا دخول",
    "market_quote_unavailable": "قراءة السعر الحديثة غير متاحة؛ لا دخول",
    "market_quote_stale": "قراءة السعر قديمة؛ أُلغي اقتراح الدخول",
    "market_price_moved": "تحرك السعر بعيدًا عن المرجع؛ أُلغي اقتراح الدخول",
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


def format_local(stamp):
    period = "ص" if stamp.hour < 12 else "م"
    hour = stamp.hour % 12 or 12
    return f"{stamp:%d/%m} {hour:02d}:{stamp:%M} {period}"


def local_time(value):
    return format_local(datetime.fromtimestamp(value, LOCAL))


def price_time(decision):
    try:
        stamp = datetime.fromisoformat(decision['price_time'])
        if stamp.tzinfo is None:
            return 'غير متاح'
        return format_local(stamp.astimezone(LOCAL))
    except (KeyError, TypeError, ValueError):
        return 'غير متاح'


def fully_qualified(decision, side):
    checks = decision.get('checks', {}).get(side, [])
    return (decision.get('side') == side and not decision.get('forced', False)
            and decision.get('reason') != 'best_available_bias'
            and len(checks) == 7 and sum(checks) >= 6
            and all(checks[i] for i in (0, 1, 3, 4, 6)))


def trade_strength(decision, side):
    """Presentation score only: map the existing seven checks onto a 10-point scale."""
    checks = decision.get('checks', {}).get(side, [])
    if checks:
        return round(sum(bool(x) for x in checks) / len(checks) * 10, 1)
    raw = decision.get('buy' if side == 'BUY' else 'sell', 0)
    return round(raw / 7 * 10, 1)


def signal_assessment(decision, side):
    """Rule-based evidence grade, not an estimated win probability or entry gate."""
    checks = decision.get('checks', {}).get(side, [])
    other = 'SELL' if side == 'BUY' else 'BUY'
    opposite = decision.get('checks', {}).get(other, [])
    context = decision.get('context') or {}
    if (side not in ('BUY', 'SELL') or len(checks) != 7 or len(opposite) != 7
            or any(type(x) is not bool for x in checks + opposite)):
        return 'غير قابلة للتقييم', 'لا اتجاه محدد أو بيانات الشروط غير مكتملة', []
    missing = [label for label, ok in zip(CHECK_LABELS, checks) if not ok]
    score, opposing = sum(checks), sum(opposite)
    if not context or context.get('phase') == 'unclear':
        return 'غير قابلة للتقييم', 'سياق الاتجاه غير مكتمل أو غير محسوم', missing
    phase = context.get('phase')
    reasons = {'pullback':'تصحيح محتمل؛ عودة الاتجاه لم تتأكد',
               'conflict':'تعارض بين بنية الحركة القصيرة واتجاه الساعة',
               'trend_break':'كسر نطاق الاتجاه؛ الفكرة تحتاج إعادة تقييم'}
    if phase in reasons:
        return 'ضعيفة', reasons[phase], missing
    if context.get('trend') != side:
        return 'ضعيفة', 'اتجاه الإشارة يعاكس اتجاه الساعة أو أن اتجاه الساعة غير محسوم', missing
    if context.get('local_structure') not in (side, 'WAIT'):
        return 'ضعيفة', 'بنية القمم والقيعان القصيرة تعاكس الإشارة أو غير متاحة', missing
    if phase != 'aligned' or not context.get('entry_allowed'):
        return 'ضعيفة', 'السياق لا يؤكد صلاحية الاتجاه', missing
    # Missing RSI/extension protection must not be hidden by a high total score.
    if not all(checks[i] for i in (0, 1, 2, 3, 6)):
        return 'ضعيفة', 'نقص في توافق الاتجاه أو الزخم أو نطاق RSI أو عدم التمدد', missing
    if score <= opposing:
        return 'ضعيفة', 'لا أفضلية واضحة على الشروط المعاكسة', missing
    if (fully_qualified(decision, side) and checks[2]
            and context.get('local_structure') == side and score-opposing >= 3):
        return 'قوية', 'اتجاه 15د والساعة والزخم والبنية القصيرة متوافقة مع شروط الدخول', missing
    return 'متوسطة', 'الاتجاه والزخم متوافقان؛ تأكيد البنية القصيرة أو بقية شروط الدخول ناقص', missing


def strength_message(decision, side, current=False):
    grade, reason, missing = signal_assessment(decision, side)
    name = {'BUY':'الشراء', 'SELL':'البيع'}.get(side, 'الإشارة')
    title = ('قوة دعم ' if current else 'قوة إشارة ') + name + (' الآن' if current else '')
    text = f'⭐ <b>{title}: {grade}</b>\nالسبب: {reason}'
    if missing:
        text += '\nالشروط الناقصة: ' + '، '.join(missing)
    return text + '\nتقييم قواعد النموذج؛ ليس نسبة نجاح أو ضمان ربح.'


def correction_estimate(trade, decision):
    """Heuristic display estimate; it does not alter entries, stops or targets."""
    direction = 1 if trade['side'] == 'BUY' else -1
    atr = max(float(decision.get('atr') or 0), abs(trade['entry'] - trade['stop']) / 1.4)
    context = decision.get('context') or {}
    pivot = context.get('resistance') if direction == 1 else context.get('support')
    tp1, tp2, entry_price = trade['tp1'], trade['tp2'], trade['entry']

    # Prefer a nearby prior resistance/support when it lies on the path to or just beyond TP2.
    if isinstance(pivot, (int, float)) and direction * (pivot - entry_price) > 0 and direction * (pivot - tp2) <= 0.5 * atr:
        start = float(pivot)
        source = 'دعم/مقاومة سابقة'
    else:
        start = tp1
        source = 'منطقة الهدف الأول والتمدد السعري'

    half_width = max(0.10 * atr, 0.20)
    start_low, start_high = start - half_width, start + half_width
    pullback = max(0.55 * atr, half_width * 2)
    target = start - direction * pullback
    target_half = max(0.12 * atr, 0.20)
    target_low, target_high = target - target_half, target + target_half

    # A descriptive likelihood based on current counter-pressure, not a calibrated probability.
    opposite = decision.get('sell', 0) if direction == 1 else decision.get('buy', 0)
    phase = context.get('phase')
    rsi = float(decision.get('rsi') or 50)
    pressure = opposite
    if phase in ('pullback', 'conflict'):
        pressure += 2
    if (direction == 1 and rsi >= 65) or (direction == -1 and rsi <= 35):
        pressure += 1
    likelihood = 'مرتفع' if pressure >= 6 else 'متوسط' if pressure >= 4 else 'ضعيف'
    correction_side = '🔴 بيعي' if direction == 1 else '🟢 شرائي'
    return correction_side, likelihood, start_low, start_high, target_low, target_high, source


def entry(trade, decision):
    side = "🟢 شراء BUY" if trade["side"] == "BUY" else "🔴 بيع SELL"
    grade = ('مستوفية شروط الدخول — غير مضمونة' if fully_qualified(decision, trade['side'])
             else 'ترجيح أولي — غير مضمون، خطر مرتفع')
    corr_side, corr_level, start_lo, start_hi, target_lo, target_hi, corr_source = correction_estimate(trade, decision)
    return (f"🥇 <b>XAU/USD | إشارة ليث</b>\n"
            f"{strength_message(decision, trade['side'])}\n\n"
            f"📌 الصفقة: <b>{side}</b>\n"
            f"💰 سعر الإشارة المرجعي: <b>{trade['entry']:.2f}</b>\n"
            "المصدر: Twelve Data؛ ليس سعر شراء/بيع مباشر من JustMarkets.\n"
            f"وقت قراءة السعر: {local_time(trade.get('quote_time',trade['created']))} فلسطين\n"
            f"🛑 وقف الخسارة: <b>{trade['stop']:.2f}</b>\n\n"
            f"🎯 <b>الأهداف</b>\n"
            f"TP1 — <b>{trade['tp1']:.2f}</b>\n"
            f"TP2 — <b>{trade['tp2']:.2f}</b>\n\n"
            f"📊 <b>قوة الشروط</b>\n"
            f"🟢 شراء: <b>{decision['buy']}/7</b>\n"
            f"🔴 بيع: <b>{decision['sell']}/7</b>\n\n"
            f"🔄 <b>التصحيح المحتمل: {corr_side}</b>\n"
            f"قوة الاحتمال التحليلية: <b>{corr_level}</b>\n"
            f"منطقة بداية التصحيح المقدّرة: <b>{start_lo:.2f}–{start_hi:.2f}</b>\n"
            f"منطقة وصول التصحيح المقدّرة: <b>{target_lo:.2f}–{target_hi:.2f}</b>\n"
            f"الأساس: {corr_source} + ATR والزخم والسياق الحالي.\n"
            "<i>هذه منطقة اجتهادية متغيرة وليست أمر دخول عكسي.</i>\n\n"
            f"⚠️ إلغاء السيناريو/الوقف: <b>{trade['stop']:.2f}</b>\n"
            f"الحالة: {grade}\n"
            f"المرجع: <code>{escape(trade['id'])}</code>\n"
            f"آخر إغلاق 5د: {price_time(decision)} فلسطين\n"
            f"وقت الإشارة: {local_time(trade['created'])} فلسطين\n\n"
            "لا تنفّذ على رقم الرسالة إذا اختلف سعر وسيطك؛ المرجع ليس سعر تنفيذ مضمونًا.\n"
            "التحديث كل 5د كردّ على هذه الرسالة. التنفيذ والوقف عند وسيطك.")


def transition(trade, kind):
    side = 'شراء' if trade['side'] == 'BUY' else 'بيع'
    reference = f"{side} | المرجع: <code>{escape(trade['id'])}</code>\n"
    if kind == 'protect':
        return ('🛡️ <b>تحديث الوقف التدريجي المقترح</b>\n' + reference +
                f"الوقف الجديد: <b>{trade['stop']:.2f}</b>\n" +
                'تحريك باتجاه الحماية فقط؛ طبّقه يدويًا إذا سمح سعر وسيطك.\n'
                'ليس تأمينًا مضمونًا؛ الرسوم والانزلاق غير محسوبة.')
    if kind == "tp1":
        return ("🎯 <b>رُصد الهدف الأول</b>\n" + reference +
                f"\nالهدف الأول: <b>{trade['tp1']:.2f}</b>\n"
                f"الهدف التالي: <b>{trade['tp2']:.2f}</b>\n"
                f"الحماية المقترحة: <b>{trade['stop']:.2f}</b>؛ لا تُرجع الوقف للخلف\n\n"
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
    text += "طوارئ مستقلة على شموع الدقيقة؛ ترسل عند تحقق الحدث ببيانات حديثة. لا إغلاق آلي.\n"
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
            "لا تنتظر الرسائل لتنفيذ وقفك؛ البيانات قد تتأخر.")
