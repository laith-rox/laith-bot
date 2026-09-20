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

    reasons = list(gate.get("reasons") or [])
    if extra_reason and extra_reason not in reasons:
        reasons.append(extra_reason)
    if nearby or news_reason == "news_blackout":
        reasons.append("news_blackout")
    elif news_reason == "calendar_unavailable":
        reasons.append("calendar_unavailable")
    reasons = list(dict.fromkeys(reasons))
    short_reasons = " — ".join(_reason(item) for item in reasons[:2])
    if not short_reasons:
        short_reasons = "الشروط لم تكتمل بما يكفي"

    side = intelligence.get("preferred_side", "—")
    trigger = plan.get("buy_trigger") if side == "BUY" else plan.get("sell_trigger")
    opposite = plan.get("sell_trigger") if side == "BUY" else plan.get("buy_trigger")
    action_word = "شراء" if side == "BUY" else "بيع" if side == "SELL" else str(side)
    opposite_word = "بيع" if side == "BUY" else "شراء" if side == "SELL" else "المعاكس"
    news_state = "انتظار/حظر" if nearby or news_reason != "calendar_clear" else "واضحة"

    return (
        "⏳ <b>V4 — انتظار</b>\n"
        f"🔵① جودة السيناريو: <b>{confidence.get('score', '—')}/10 — {confidence.get('label', '—')}</b>\n"
        f"🟠② تفعيل {action_word}: <b>{_fmt(trigger)}</b>\n"
        f"🔴③ الإبطال: <b>{_fmt(inv.get('level'))}</b>\n"
        f"🟡④ المستوى المعاكس ({opposite_word}): {_fmt(opposite)}\n"
        f"⛔️⑤ السبب: {short_reasons}\n"
        f"🔵⑥ الأخبار/البيانات: {news_state} | {data.get('label', '—')} ({data.get('bar_age_seconds', '—')}ث)\n"
        "✅ الحالة: لا دخول الآن"
    )
