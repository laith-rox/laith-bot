"""Auditable Quick entry policy. Scores are rule evidence, not win probabilities."""
import math


def assess_entry(decision, setup, reference, now, *, cached=False, news_clear=True):
    result = {"action": "WATCH", "reasons": [], "warnings": [], "policy": "flex-v1"}
    def stop(reason):
        result["reasons"].append(reason)
        return result
    side = setup.get("side")
    if side not in ("BUY", "SELL"):
        return stop("اتجاه الصفقة غير محدد")
    sign = 1 if side == "BUY" else -1
    try:
        price, sl, tp = (float(setup[k]) for k in ("entry", "stop", "target"))
        stamp, atr = float(reference["time"]), float(decision["atr"])
        opening = float(reference["candle_open"])
        if not all(math.isfinite(v) for v in (price, sl, tp, stamp, atr, opening)):
            raise ValueError()
        if min(price, sl, tp, atr, opening) <= 0 or sign*(price-sl) <= 0 or sign*(tp-price) <= 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        return stop("سعر الدخول أو الوقف أو الهدف غير صالح")
    age = now.timestamp() - stamp
    result["reference_age_seconds"] = round(age, 2)
    if age < -5 or age > 90 or cached or not reference.get("timing_aligned"):
        return stop("السعر قديم أو توقيته غير موثوق؛ انتظار تحديث")
    research = decision.get("v4") or {}
    reasons = ((research.get("intelligence") or {}).get("entry_gate") or {}).get("reasons") or []
    if set(reasons) & {"recent_data_gap", "stale_market_data"}:
        return stop("بيانات الشموع قديمة أو فيها فجوة")
    checks = (decision.get("checks") or {}).get(side) or []
    if len(checks) != 7 or any(type(v) is not bool for v in checks):
        return stop("بيانات شروط الفرصة غير مكتملة")
    score = sum(checks)
    result["score"] = score
    higher = (decision.get("quick5m") or {}).get("higher_side", "WAIT")
    # Local trend and momentum can confirm a Quick while the official setup waits.
    trend = higher == side or (higher == "WAIT" and checks[1] and checks[2])
    momentum = checks[0] and (checks[3] or checks[4])
    location = abs(price-opening) <= atr and abs(price-float((decision.get("quick5m") or {}).get("ema9", price))) <= 1.5*atr
    result["essentials"] = {"trend": trend, "momentum": momentum, "location": location}
    if not trend:
        return stop("انتظار توافق الاتجاه؛ الحركة الحالية قد تكون تصحيحًا")
    if not momentum:
        return stop("انتظار تأكيد حركة 5د باتجاه الفرصة")
    if not location:
        return stop("السعر ابتعد عن منطقة الدخول؛ انتظار رجعة أو إعادة اختبار")
    if score < 5:
        return stop("الفرصة تحت المراقبة؛ الشروط أقل من ٥/٧")
    warnings = result["warnings"]
    if reference.get("delayed_reference"):
        warnings.append("المرجع إغلاق شمعة حديثة وليس سعرًا حيًا")
    if higher != side:
        warnings.append("الاتجاه الأكبر محايد؛ الاعتماد على اتجاه وزخم 5د")
    if not news_clear:
        warnings.append("الأخبار قريبة أو تقويمها غير مؤكد")
    if reasons:
        warnings.append("توجد تحذيرات هيكلية")
    if research.get("macro_alignment") in ("OPPOSE", "STRONG_OPPOSE", "CONFLICT"):
        warnings.append("العوامل الخارجية غير متوافقة")
    result["action"] = "ENTER_NOW" if score >= 6 and age <= 30 and not warnings else "CAUTIOUS"
    result["reasons"] = ["اتجاه وزخم ومكان دخول متوافقون"]
    return result
