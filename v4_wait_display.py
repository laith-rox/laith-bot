"""Arabic display for V4 smart WAIT plans."""

REASON_AR = {
    "compressed_between_support_resistance": "السعر محصور بين دعم ومقاومة قريبين؛ مساحة الحركة غير كافية",
    "opposing_structure_too_close": "يوجد مستوى مقابل قريب يجعل العائد مقابل المخاطرة ضعيفًا",
    "failed_breakout": "ظهر كسر فاشل؛ الدخول الآن معرض للارتداد",
    "extreme_volatility": "التذبذب متطرف؛ مكان الوقف والدخول غير مستقر",
    "strong_adverse_correction": "يوجد تصحيح قوي بعكس اتجاه الدخول المقترح",
    "recent_data_gap": "هناك فجوة في بيانات الشموع الأخيرة",
    "stale_market_data": "بيانات السوق أقدم من الحد المسموح للدخول",
    "market_price_moved": "السعر تحرك عن سعر التحليل قبل تأكيد الدخول",
    "calendar_unavailable": "تقويم الأخبار غير موثوق حاليًا؛ لا دخول رسمي",
    "news_blackout": "خبر أمريكي قوي قريب أو صدر حديثًا",
    "quick_data_incomplete": "بيانات الإشارة غير مكتملة",
    "quick_recheck_failed": "الإشارة لم تصمد عند إعادة الفحص",
}


def _fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _reason(value):
    return REASON_AR.get(str(value), str(value).replace("_", " "))


def smart_wait_message(decision, news_reason=None, nearby=False, extra_reason=None):
    research = decision.get("v4") or {}
    intelligence = research.get("intelligence") or {}
    gate = intelligence.get("entry_gate") or {}
    plan = intelligence.get("wait_plan") or {}
    inv = intelligence.get("invalidation") or {}
    confidence = intelligence.get("confidence") or {}
    data = intelligence.get("data_quality") or {}
    components = confidence.get("components") or {}

    reasons = list(gate.get("reasons") or [])
    if extra_reason and extra_reason not in reasons:
        reasons.append(extra_reason)
    if nearby or news_reason == "news_blackout":
        reasons.append("news_blackout")
    elif news_reason == "calendar_unavailable":
        reasons.append("calendar_unavailable")
    reasons = list(dict.fromkeys(reasons))
    reason_text = "\n".join("• " + _reason(item) for item in reasons)
    if not reason_text:
        reason_text = "• الشروط لم تكتمل بما يكفي للدخول الآن"

    side = intelligence.get("preferred_side", "—")
    trigger = plan.get("buy_trigger") if side == "BUY" else plan.get("sell_trigger")
    opposite = plan.get("sell_trigger") if side == "BUY" else plan.get("buy_trigger")
    action_word = "شراء" if side == "BUY" else "بيع" if side == "SELL" else str(side)
    opposite_word = "بيع" if side == "BUY" else "شراء" if side == "SELL" else "المعاكس"

    return (
        "⏳ <b>V4 — انتظار ذكي / لا دخول الآن</b>\n\n"
        f"الاتجاه المفضل للمراقبة: <b>{side}</b>\n"
        f"🚫 لماذا ننتظر:\n{reason_text}\n\n"
        f"🧪 جودة السيناريو: <b>{confidence.get('score', '—')}/10 — {confidence.get('label', '—')}</b>\n"
        f"اتجاه {components.get('trend', '—')}/10 | زخم {components.get('momentum', '—')}/10 | "
        f"هيكل {components.get('structure', '—')}/10 | دخول {components.get('entry_quality', '—')}/10\n"
        f"ماكرو {components.get('macro', '—')}/10 | تذبذب {components.get('volatility', '—')}/10 | "
        f"بيانات {components.get('data_quality', '—')}/10\n"
        f"📰 الأخبار: {'حظر/انتظار' if nearby or news_reason != 'calendar_clear' else 'واضحة لحظة الفحص'}\n"
        f"📡 جودة البيانات: {data.get('label', '—')} | عمر آخر شمعة: {data.get('bar_age_seconds', '—')}ث\n\n"
        f"✅ تفعيل {action_word} المشروط قرب: <b>{_fmt(trigger)}</b>\n"
        f"↔️ المستوى المعاكس للمراقبة ({opposite_word}): {_fmt(opposite)}\n"
        f"🔎 التأكيد: {plan.get('confirmation', 'إغلاق M15 خلف المستوى ثم ثبات/إعادة اختبار')}\n"
        f"🧱 إبطال السيناريو المفضل: <b>{_fmt(inv.get('level'))}</b> — {inv.get('rule', '—')}\n\n"
        "الجودة هنا تقييم للشروط وليست نسبة ربح. لا يتم فتح أي صفقة تلقائيًا."
    )
