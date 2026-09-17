"""Laith V4 decision intelligence and learning helpers.

This module is V4-only.  It adds descriptive quality scoring, smart no-entry
zones, conditional wait plans, invalidation maps and post-trade learning.  Scores
are rule-quality summaries, never calibrated probabilities of profit.
"""
from collections import Counter
from copy import deepcopy
import math


CONDITION_LABELS = (
    "اتجاه M15",
    "اتجاه H1",
    "زخم MACD",
    "RSI مناسب",
    "موقع السعر من EMA20",
    "شمعة M15 مؤيدة",
    "السعر غير متمدد",
)


def _num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clamp(value, low=0.0, high=10.0):
    return max(low, min(high, float(value)))


def _side_hint(decision):
    side = decision.get("side")
    if side in ("BUY", "SELL"):
        return side
    try:
        buy = int(decision.get("buy", 0) or 0)
        sell = int(decision.get("sell", 0) or 0)
    except (TypeError, ValueError):
        buy = sell = 0
    if buy > sell:
        return "BUY"
    if sell > buy:
        return "SELL"
    trend = str((decision.get("context") or {}).get("trend") or "")
    if trend in ("BUY", "SELL"):
        return trend
    rsi = _num(decision.get("rsi"), 50.0)
    return "BUY" if rsi >= 50.0 else "SELL"


def _checks(decision, side):
    raw = (decision.get("checks") or {}).get(side)
    if not isinstance(raw, (list, tuple)) or len(raw) != 7:
        return [False] * 7
    return [bool(item) for item in raw]


def _bar_quality(bars, now):
    if not bars:
        return {
            "label": "UNAVAILABLE", "score": 0, "bar_age_seconds": None,
            "recent_gap": True, "reason": "no_bars",
        }
    last = bars[-1]
    try:
        age = max(0.0, now.timestamp() - last.end.timestamp())
    except Exception:
        age = None
    recent = bars[-5:]
    gap = False
    if len(recent) >= 2:
        try:
            gap = any(abs((b.start - a.start).total_seconds() - 300) > 1 for a, b in zip(recent, recent[1:]))
        except Exception:
            gap = True
    if gap:
        label, score, reason = "GAP", 1, "recent_data_gap"
    elif age is None:
        label, score, reason = "UNAVAILABLE", 2, "bar_age_unknown"
    elif age <= 180:
        label, score, reason = "FRESH", 10, "fresh_closed_data"
    elif age <= 360:
        label, score, reason = "USABLE", 8, "closed_data_aging"
    elif age <= 600:
        label, score, reason = "AGING", 5, "closed_data_old"
    else:
        label, score, reason = "STALE", 0, "closed_data_stale"
    return {
        "label": label,
        "score": score,
        "bar_age_seconds": round(age, 1) if age is not None else None,
        "recent_gap": bool(gap),
        "reason": reason,
    }


def _no_trade_zone(decision, research):
    price = _num(decision.get("price"))
    atr = _num(decision.get("atr"))
    support = research.get("nearest_support") or {}
    resistance = research.get("nearest_resistance") or {}
    breakout = research.get("breakout_state")
    risk = research.get("structural_risk") or {}
    reasons = []
    details = {}

    if risk.get("valid") is False and risk.get("reason") == "opposing_structure_too_close":
        reasons.append("opposing_structure_too_close")

    if price is not None and atr and atr > 0 and support and resistance:
        s_high = _num(support.get("high"))
        r_low = _num(resistance.get("low"))
        if s_high is not None and r_low is not None and r_low >= s_high:
            corridor = r_low - s_high
            support_gap = max(0.0, price - s_high)
            resistance_gap = max(0.0, r_low - price)
            details.update(
                corridor=round(corridor, 5),
                corridor_atr=round(corridor / atr, 3),
                support_gap_atr=round(support_gap / atr, 3),
                resistance_gap_atr=round(resistance_gap / atr, 3),
            )
            compressed = corridor <= 1.10 * atr
            centered = support_gap <= 0.55 * atr and resistance_gap <= 0.55 * atr
            if breakout == "LEVEL_INTACT" and compressed and centered:
                reasons.append("compressed_between_support_resistance")

    correction = research.get("correction") or {}
    hint = _side_hint(decision)
    adverse = (
        correction.get("triggered")
        and correction.get("strength") == "STRONG"
        and ((hint == "BUY" and correction.get("direction") == "DOWN")
             or (hint == "SELL" and correction.get("direction") == "UP"))
    )
    if breakout == "FAILED_BREAK":
        reasons.append("failed_breakout")
    if research.get("volatility_regime") == "EXTREME":
        reasons.append("extreme_volatility")
    if adverse:
        reasons.append("strong_adverse_correction")

    return {
        "active": bool(reasons),
        "reasons": list(dict.fromkeys(reasons)),
        "details": details,
    }


def _invalidation_plan(decision, research, side):
    atr = _num(decision.get("atr"))
    risk = research.get("structural_risk") or {}
    support = research.get("nearest_support") or {}
    resistance = research.get("nearest_resistance") or {}
    level = _num(risk.get("stop"))
    source = "structural_stop" if level is not None else None
    buffer = 0.10 * atr if atr and atr > 0 else 0.0
    if level is None and side == "BUY":
        anchor = _num(support.get("low"))
        if anchor is not None:
            level, source = anchor - buffer, "support_break"
    if level is None and side == "SELL":
        anchor = _num(resistance.get("high"))
        if anchor is not None:
            level, source = anchor + buffer, "resistance_break"
    if level is None:
        return {"level": None, "rule": "غير متاح", "source": "unavailable"}
    return {
        "level": round(level, 5),
        "rule": "إغلاق M15 تحت المستوى" if side == "BUY" else "إغلاق M15 فوق المستوى",
        "source": source,
    }


def _wait_plan(decision, research, side):
    price = _num(decision.get("price"))
    atr = _num(decision.get("atr"))
    if price is None or not atr or atr <= 0:
        return {"mode": "WAIT", "preferred_side": side, "buy_trigger": None, "sell_trigger": None}
    support = research.get("nearest_support") or {}
    resistance = research.get("nearest_resistance") or {}
    buffer = 0.10 * atr
    r_high = _num(resistance.get("high"))
    s_low = _num(support.get("low"))
    buy_trigger = (r_high + buffer) if r_high is not None else price + 0.35 * atr
    sell_trigger = (s_low - buffer) if s_low is not None else price - 0.35 * atr
    return {
        "mode": "WAIT",
        "preferred_side": side,
        "buy_trigger": round(buy_trigger, 5),
        "sell_trigger": round(sell_trigger, 5),
        "confirmation": "إغلاق M15 خلف المستوى ثم ثبات/إعادة اختبار بدون رجوع سريع داخل المنطقة",
    }


def _confidence(decision, research, side, zone, data_quality):
    checks = _checks(decision, side)
    trend = 10 * sum(checks[:2]) / 2
    momentum = 10 * sum((checks[2], checks[3], checks[5])) / 3
    entry = 10 * sum((checks[4], checks[6])) / 2

    breakout = research.get("breakout_state")
    structure = {
        "RETEST_HELD": 10, "CONFIRMED_BREAK": 9, "OPEN_SPACE": 8,
        "LEVEL_INTACT": 6, "UNAVAILABLE": 5, "FAILED_BREAK": 1,
    }.get(str(breakout), 5)
    risk = research.get("structural_risk") or {}
    if risk.get("valid") is False:
        structure = min(structure, 3)

    macro = {
        "STRONG_ALIGN": 10, "ALIGN": 8, "NEUTRAL": 6,
        "UNAVAILABLE": 5, "CONFLICT": 3, "STRONG_CONFLICT": 0,
    }.get(str(research.get("macro_alignment")), 5)
    volatility = {
        "NORMAL": 9, "LOW": 7, "HIGH": 5, "EXTREME": 1, "UNAVAILABLE": 5,
    }.get(str(research.get("volatility_regime")), 5)
    data = _clamp(data_quality.get("score", 5))
    if zone.get("active"):
        entry = min(entry, 3)
        structure = min(structure, 3)

    components = {
        "trend": round(_clamp(trend), 1),
        "momentum": round(_clamp(momentum), 1),
        "structure": round(_clamp(structure), 1),
        "entry_quality": round(_clamp(entry), 1),
        "macro": round(_clamp(macro), 1),
        "volatility": round(_clamp(volatility), 1),
        "data_quality": round(_clamp(data), 1),
    }
    total = (
        components["trend"] * 0.18
        + components["momentum"] * 0.15
        + components["structure"] * 0.22
        + components["entry_quality"] * 0.18
        + components["macro"] * 0.10
        + components["volatility"] * 0.07
        + components["data_quality"] * 0.10
    )
    if total >= 8.0:
        label = "قوية"
    elif total >= 6.5:
        label = "جيدة"
    elif total >= 5.0:
        label = "متوسطة"
    else:
        label = "ضعيفة"
    return {"score": round(total, 1), "label": label, "components": components,
            "calibrated_probability": False}


def enrich_decision(decision, bars, now):
    """Attach V4-only guard, wait, invalidation and confidence fields.

    A hard smart-zone block can convert an otherwise actionable V4 decision to
    WAIT.  It never turns a WAIT decision into BUY/SELL.
    """
    result = deepcopy(decision)
    research = dict(result.get("v4") or {})
    side = _side_hint(result)
    checks = _checks(result, side)
    quality = _bar_quality(bars, now)
    zone = _no_trade_zone(result, research)

    hard_reasons = list(zone.get("reasons") or [])
    if quality.get("recent_gap"):
        hard_reasons.append("recent_data_gap")
    if quality.get("label") == "STALE":
        hard_reasons.append("stale_market_data")
    hard_reasons = list(dict.fromkeys(hard_reasons))

    gate = {
        "allowed": not hard_reasons,
        "hard_block": bool(hard_reasons),
        "reasons": hard_reasons,
        "primary_reason": hard_reasons[0] if hard_reasons else "clear",
        "no_trade_zone": zone,
    }
    confidence = _confidence(result, research, side, zone, quality)
    invalidation = _invalidation_plan(result, research, side)
    wait_plan = _wait_plan(result, research, side)

    setup_reasons = [label for label, ok in zip(CONDITION_LABELS, checks) if ok]
    missing = [label for label, ok in zip(CONDITION_LABELS, checks) if not ok]
    breakout = research.get("breakout_state")
    if breakout in ("CONFIRMED_BREAK", "RETEST_HELD"):
        setup_reasons.append("الكسر/إعادة الاختبار مؤكد")
    if research.get("macro_alignment") in ("ALIGN", "STRONG_ALIGN"):
        setup_reasons.append("الماكرو متوافق")

    correction = dict(research.get("correction") or {})
    if correction:
        correction["state"] = "TRIGGERED" if correction.get("triggered") else "WATCH"
        t1, t2 = _num(correction.get("target1")), _num(correction.get("target2"))
        if t1 is not None or t2 is not None:
            correction["expected_range"] = [t1, t2]
        research["correction"] = correction

    intelligence = {
        "preferred_side": side,
        "entry_gate": gate,
        "confidence": confidence,
        "invalidation": invalidation,
        "wait_plan": wait_plan,
        "data_quality": quality,
        "setup_reasons": setup_reasons,
        "missing_conditions": missing,
    }
    research["intelligence"] = intelligence
    result["v4"] = research

    if result.get("side") in ("BUY", "SELL") and gate["hard_block"]:
        result["side"] = "WAIT"
        mapping = {
            "compressed_between_support_resistance": "v4_no_trade_zone",
            "opposing_structure_too_close": "v4_no_trade_zone",
            "failed_breakout": "v4_failed_breakout_wait",
            "extreme_volatility": "v4_extreme_volatility_wait",
            "strong_adverse_correction": "v4_adverse_correction_wait",
            "recent_data_gap": "v4_data_gap_wait",
            "stale_market_data": "v4_stale_data_wait",
        }
        result["reason"] = mapping.get(gate["primary_reason"], "v4_smart_entry_guard")
    return result


def quick_hard_blocked(decision):
    intelligence = ((decision.get("v4") or {}).get("intelligence") or {})
    return bool((intelligence.get("entry_gate") or {}).get("hard_block"))


def attach_continuation_intelligence(snapshot, decision, trade):
    if snapshot is None:
        return None
    result = dict(snapshot)
    intelligence = ((decision.get("v4") or {}).get("intelligence") or {})
    result["confidence"] = intelligence.get("confidence") or {}
    result["invalidation"] = intelligence.get("invalidation") or {}
    result["data_quality"] = intelligence.get("data_quality") or {}
    result["wait_plan"] = intelligence.get("wait_plan") or {}
    price = _num(result.get("price"))
    entry = _num(trade.get("entry"))
    initial_sl = _num(trade.get("initial_sl", trade.get("stop")))
    if price is not None and entry is not None and initial_sl is not None and abs(entry - initial_sl) > 1e-9:
        direction = 1 if trade.get("side") == "BUY" else -1
        result["progress_r"] = round(direction * (price - entry) / abs(entry - initial_sl), 2)
    return result


def _fmt(value):
    number = _num(value)
    return "—" if number is None else f"{number:.2f}"


def _confidence_line(confidence):
    if not confidence:
        return None
    c = confidence.get("components") or {}
    return (
        f"🧪 جودة الإشارة: <b>{confidence.get('score', '—')}/10 — {confidence.get('label', '—')}</b> "
        f"| اتجاه {c.get('trend', '—')} | زخم {c.get('momentum', '—')} | هيكل {c.get('structure', '—')} | دخول {c.get('entry_quality', '—')}"
    )


def wait_message(decision, news_reason=None, nearby=False, extra_reason=None):
    research = decision.get("v4") or {}
    intelligence = research.get("intelligence") or {}
    gate = intelligence.get("entry_gate") or {}
    plan = intelligence.get("wait_plan") or {}
    inv = intelligence.get("invalidation") or {}
    confidence = intelligence.get("confidence") or {}
    reasons = list(gate.get("reasons") or [])
    if extra_reason and extra_reason not in reasons:
        reasons.append(extra_reason)
    if nearby or news_reason == "news_blackout":
        reasons.append("خبر أمريكي قوي قريب/حديث")
    reason_text = " — ".join(str(x) for x in reasons) if reasons else str(decision.get("reason") or "الشروط غير مكتملة")
    conf_line = _confidence_line(confidence) or "🧪 جودة الإشارة: غير متاحة"
    return (
        "⏳ <b>V4 — وضع انتظار / لا دخول الآن</b>\n\n"
        f"الاتجاه المفضل للمراقبة: <b>{intelligence.get('preferred_side', '—')}</b>\n"
        f"🚫 السبب: {reason_text}\n"
        f"{conf_line}\n"
        f"🟢 تفعيل شراء مشروط فوق: <b>{_fmt(plan.get('buy_trigger'))}</b>\n"
        f"🔴 تفعيل بيع مشروط تحت: <b>{_fmt(plan.get('sell_trigger'))}</b>\n"
        f"✅ التأكيد المطلوب: {plan.get('confirmation', 'إغلاق M15 وثبات') }\n"
        f"🧱 إبطال السيناريو المفضل: {_fmt(inv.get('level'))} — {inv.get('rule', '—')}\n\n"
        "هذه مستويات مراقبة مشروطة وليست ضمانًا أو أمر دخول تلقائي."
    )


def enhance_quick_message(message, trade):
    intelligence = trade.get("intelligence") or {}
    confidence = intelligence.get("confidence") or {}
    inv = intelligence.get("invalidation") or {}
    plan = intelligence.get("wait_plan") or {}
    reasons = intelligence.get("setup_reasons") or []
    missing = intelligence.get("missing_conditions") or []
    lines = message.splitlines()
    insert_at = len(lines)
    for index, line in enumerate(lines):
        if line.startswith("⚠️ نسبة الشروط"):
            insert_at = index
            break
    extra = []
    conf_line = _confidence_line(confidence)
    if conf_line:
        extra.append(conf_line)
    if inv.get("level") is not None:
        extra.append(f"🧱 إبطال السيناريو: <b>{_fmt(inv.get('level'))}</b> — {inv.get('rule', '—')}")
    if reasons:
        extra.append("✅ أسباب داعمة: " + "، ".join(str(x) for x in reasons[:4]))
    if missing:
        extra.append("⚠️ شروط ناقصة: " + "، ".join(str(x) for x in missing[:3]))
    if trade.get("official_decision") == "WAIT" and plan:
        preferred = plan.get("preferred_side")
        trigger = plan.get("buy_trigger") if preferred == "BUY" else plan.get("sell_trigger")
        extra.append(f"⏳ الرسمي WAIT: راقب تفعيل {preferred} قرب <b>{_fmt(trigger)}</b> بعد تأكيد M15")
    if extra:
        lines[insert_at:insert_at] = [""] + extra + [""]
    return "\n".join(lines)


def enhance_continuation_message(message, snapshot):
    confidence = snapshot.get("confidence") or {}
    inv = snapshot.get("invalidation") or {}
    data = snapshot.get("data_quality") or {}
    extra = []
    conf_line = _confidence_line(confidence)
    if conf_line:
        extra.append(conf_line)
    if snapshot.get("progress_r") is not None:
        extra.append(f"📐 تقدم الصفقة: <b>{snapshot.get('progress_r')}R</b>")
    if inv.get("level") is not None:
        extra.append(f"🧱 إبطال السيناريو: <b>{_fmt(inv.get('level'))}</b> — {inv.get('rule', '—')}")
    extra.append(f"📡 جودة البيانات: {data.get('label', '—')} | عمر آخر شمعة: {data.get('bar_age_seconds', '—')}ث")
    return message + ("\n" + "\n".join(extra) if extra else "")


def enhance_paper_open_message(message, trade):
    intelligence = ((trade.get("research_v4") or {}).get("intelligence") or {})
    confidence = intelligence.get("confidence") or {}
    inv = intelligence.get("invalidation") or {}
    reasons = intelligence.get("setup_reasons") or []
    correction = (trade.get("research_v4") or {}).get("correction") or {}
    extra = ["", "🧠 <b>طبقة V4 الذكية</b>"]
    conf_line = _confidence_line(confidence)
    if conf_line:
        extra.append(conf_line)
    if inv.get("level") is not None:
        extra.append(f"🧱 الإبطال: {_fmt(inv.get('level'))} — {inv.get('rule', '—')}")
    if reasons:
        extra.append("✅ لماذا ظهرت الإشارة: " + "، ".join(str(x) for x in reasons[:5]))
    if correction.get("direction"):
        extra.append(
            f"↩️ التصحيح: {correction.get('direction')} / {correction.get('strength', '—')} "
            f"| بداية {_fmt((correction.get('start_zone') or {}).get('center'))} "
            f"| أهداف {_fmt(correction.get('target1'))} ثم {_fmt(correction.get('target2'))}"
        )
    extra.append("📰 حارس الأخبار: تم اجتياز فلتر الأخبار لحظة فتح الصفقة الورقية.")
    return message + "\n" + "\n".join(extra)


def classify_trade_lesson(trade):
    try:
        r_value = float(trade.get("r"))
    except (TypeError, ValueError):
        r_value = None
    if trade.get("outcome") not in ("STOP", "TIME") and not (r_value is not None and r_value < 0):
        return None
    research = trade.get("research_v4") or {}
    intelligence = research.get("intelligence") or trade.get("intelligence") or {}
    correction = research.get("correction") or {}
    side = trade.get("side")
    reason = "stop_before_followthrough"
    if (intelligence.get("data_quality") or {}).get("label") in ("GAP", "STALE"):
        reason = "data_quality"
    elif research.get("breakout_state") == "FAILED_BREAK" or trade.get("breakout_state") == "FAILED_BREAK":
        reason = "failed_breakout"
    elif (correction.get("triggered") and correction.get("strength") == "STRONG"
          and ((side == "BUY" and correction.get("direction") == "DOWN")
               or (side == "SELL" and correction.get("direction") == "UP"))):
        reason = "adverse_correction"
    elif research.get("volatility_regime") in ("HIGH", "EXTREME"):
        reason = "high_volatility"
    elif research.get("macro_alignment") in ("CONFLICT", "STRONG_CONFLICT"):
        reason = "macro_conflict"
    elif (research.get("structural_risk") or {}).get("room_r") is not None:
        try:
            if float((research.get("structural_risk") or {}).get("room_r")) < 1.4:
                reason = "opposing_structure"
        except (TypeError, ValueError):
            pass
    return {
        "reason": reason,
        "side": side,
        "outcome": trade.get("outcome"),
        "r": r_value,
        "confidence": (intelligence.get("confidence") or {}).get("score"),
        "breakout": research.get("breakout_state") or trade.get("breakout_state"),
        "volatility": research.get("volatility_regime") or trade.get("volatility_regime"),
    }


def record_trade_lesson(store, trade, stream="official"):
    lesson = trade.get("learning") or classify_trade_lesson(trade)
    if not lesson:
        return None
    trade_id = str(trade.get("id") or "")
    journal = store.get("v4_learning_journal", []) or []
    if not isinstance(journal, list):
        journal = []
    key = f"{stream}:{trade_id}"
    if any(item.get("key") == key for item in journal if isinstance(item, dict)):
        return lesson
    item = dict(lesson)
    item.update(key=key, trade_id=trade_id, stream=stream, closed=trade.get("closed"))
    journal.append(item)
    journal = journal[-200:]
    store.set("v4_learning_journal", journal)
    counts = Counter(str(item.get("reason") or "unknown") for item in journal if isinstance(item, dict))
    store.set("v4_learning_summary", {"losses": len(journal), "by_reason": dict(counts)})
    store.set("v4_last_learning", item)
    return lesson


def enhance_paper_close_message(message, trade):
    lesson = trade.get("learning") or classify_trade_lesson(trade)
    if not lesson:
        return message
    return (
        message
        + "\n\n🧠 <b>تعلم V4 من النتيجة</b>\n"
        + f"سبب الخسارة المصنف: <b>{lesson.get('reason')}</b>\n"
        + f"السياق: كسر {lesson.get('breakout', '—')} | تذبذب {lesson.get('volatility', '—')} | جودة {lesson.get('confidence', '—')}/10"
    )
