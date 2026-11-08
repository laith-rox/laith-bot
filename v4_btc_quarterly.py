"""Quarter-hour BTC Telegram research cards, including weak NO-ENTRY setups.

This path is deliberately separate from actionable BTC alerts, trade journaling,
and every broker/MT5 integration. Missing/stale observations never become levels.
"""
from datetime import timezone
from math import isfinite

from engine import atr, ema, rsi
from market import DataError

UTC = timezone.utc

REASONS = {
    "h1_h4_not_aligned": "اتجاه H1 وH4 غير متوافق",
    "btc_conditions_not_met": "شروط الدخول الفنية غير مكتملة",
    "btc_price_moved_too_far": "السعر ابتعد عن منطقة الدخول",
    "btc_false_breakout": "احتمال كسر وهمي",
    "btc_liquidity_not_confirmed": "السيولة أو إعادة الاختبار غير مؤكدة",
    "btc_sniper_not_confirmed": "توقيت M5 غير مؤكد",
    "low_volume": "حجم تداول ضعيف",
    "volume_unavailable": "حجم تداول غير متاح",
    "btc_book_spread_or_imbalance": "سبريد أو ضغط أوامر غير مناسب",
    "btc_crowded_derivatives": "ازدحام مراكز العقود",
    "btc_quote_orderbook_mismatch": "اختلاف سعر السوق ودفتر الأوامر",
    "btc_quote_stale": "السعر الحي غير موثوق",
    "btc_connection_failed": "مصدر السعر غير متصل",
    "btc_recent_data_gap": "شموع ناقصة أو منقطعة",
    "btc_insufficient_history": "بيانات الشموع غير كافية",
}


def _trend_label(value):
    return {"BUY": "شراء", "SELL": "بيع", "WAIT": "انتظار"}.get(value, "غير متاح")


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


def weak_preview(now, provider, state, aggregate):
    """Seven *descriptive* checks, never a real signal or permission to enter.

    Do not reuse a stale ticker or synthesize an entry when a provider fails.
    """
    if state.get("status") == "WAIT_DATA":
        return {"side": "WAIT", "score": None, "price": None, "reason": "missing_data"}
    try:
        bars = getattr(provider, "last_5m_bars", None)
        if not bars or not 0 <= (now - bars[-1].end).total_seconds() <= 600:
            bars = provider.candles(now, 5)
        if not bars or not 0 <= (now - bars[-1].end).total_seconds() <= 600:
            raise DataError("btc_weak_bars_stale")
        m15 = aggregate(bars, 15)
        if len(m15) < 55 or len(bars) < 70:
            raise DataError("btc_weak_history_short")
        if not 0 <= (now - m15[-1].end).total_seconds() <= 1200:
            raise DataError("btc_weak_m15_stale")
        close15 = [b.close for b in m15]
        fast, slow = ema(close15, 20)[-1], ema(close15, 50)[-1]
        h1, h4 = state.get("h1_trend"), state.get("h4_trend")
        # H4 contextual bias is preferred; H1 / M15 are only fallback hypotheses.
        side = (h4 if h4 in ("BUY", "SELL")
                else h1 if h1 in ("BUY", "SELL")
                else "BUY" if fast > slow else "SELL" if fast < slow else "WAIT")
        if side == "WAIT":
            return {"side": side, "score": 0, "price": None}
        up = side == "BUY"
        rsi5 = rsi([b.close for b in bars[-70:]])
        prev15 = m15[-9:-1]
        last15, last5 = m15[-1], bars[-1]
        breakout = (last15.close > max(b.high for b in prev15)
                    if up else last15.close < min(b.low for b in prev15))
        checks = [
            h4 == side, h1 == side,
            fast > slow if up else fast < slow,
            last15.close > last15.open if up else last15.close < last15.open,
            last5.close > last5.open if up else last5.close < last5.open,
            48 <= rsi5 <= 72 if up else 28 <= rsi5 <= 52,
            breakout,
        ]
        result = {
            "side": side, "score": sum(bool(check) for check in checks),
            "price": None, "sl": None, "tp1": None, "tp2": None,
        }
        # Live Coinbase spot quote only; never present prior candle close as live entry.
        try:
            price = _num(provider.ticker(now))
        except (DataError, AttributeError, ValueError, TypeError):
            price = None
        if price is None or abs(price - last5.close) > max(price * .0015, .6 * atr(m15[-40:])):
            result["reason"] = "quote_unverified_or_moved"
            return result
        volatility = _num(atr(m15[-40:]))
        if not volatility or volatility / price > .035:
            result["reason"] = "volatility_unverified"
            return result
        distance = volatility * 1.5
        sign = 1 if up else -1
        sl = price - sign * distance
        first = price + sign * distance * 1.8
        second = price + sign * distance * 2.8
        if min(sl, first, second) <= 0:
            result["reason"] = "invalid_reference_levels"
            return result
        result.update(price=price, sl=sl, tp1=first, tp2=second)
        return result
    except (DataError, AttributeError, KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
        return {
            "side": "WAIT", "score": None, "price": None,
            "reason": f"preview_unavailable:{type(exc).__name__}",
        }


def quarterly_message(now, state, preview, note=None):
    """A research card with unequivocal NO-ENTRY label, even with mock levels."""
    local = now.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Hebron"))
    hour = local.strftime("%I:%M")
    suffix = "صباحًا" if local.hour < 12 else "مساءً"
    side = preview.get("side", "WAIT")
    chosen = "🟢 شراء افتراضي" if side == "BUY" else "🔴 بيع افتراضي" if side == "SELL" else "⚪ اتجاه غير محسوم"
    score = preview.get("score")
    score_str = f"{score}/7" if isinstance(score, int) else "غير قابل للقياس"
    reason = REASONS.get(str(state.get("reason")), str(state.get("reason") or "الشروط غير متوفرة"))
    # Restrict unsafe raw error strings to known data errors, not HTML or secrets.
    if reason not in REASONS.values() and reason not in ("الشروط غير متوفرة",):
        reason = "بيانات أو شروط الدخول غير مكتملة"
    lines = [
        "₿ <b>فكرة بيتكوين كل 15 دقيقة — مراقبة فقط</b>",
        ("⛔ <b>تحديث صفقة سابقة أو فرصة مكررة — لا تدخل الآن</b>"
         if note in ("cooldown", "active_observation", "price_moved")
         else "⛔ <b>صفقة ضعيفة / غير مؤهلة — لا تدخل الآن</b>"),
        f"📈 الميل الافتراضي: <b>{chosen}</b>",
        f"🧠 الشروط الاسترشادية: <b>{score_str}</b> (ليست نسبة نجاح)",
        f"🕓 H1: {_trend_label(state.get('h1_trend'))} | H4: {_trend_label(state.get('h4_trend'))}",
        f"🟡 سبب عدم الدخول: {reason}",
    ]
    price = _num(preview.get("price"))
    sl, tp1, tp2 = [_num(preview.get(x)) for x in ("sl", "tp1", "tp2")]
    if price and sl and tp1 and tp2:
        lines += [
            f"📍 سعر Coinbase الفوري المرجعي: {price:,.2f}$",
            f"🛑 وقف افتراضي: {sl:,.2f}$",
            f"🎯 هدف افتراضي 1: {tp1:,.2f}$",
            f"🎯 هدف افتراضي 2: {tp2:,.2f}$",
            "⚠️ هذه مستويات بحثية، لا تستخدمها للدخول؛ سعر JustMarkets ورسومه قد تختلف.",
        ]
    else:
        lines.append("📍 الدخول/الوقف/الأهداف: غير معروضة — سعر أو شروط البيانات غير موثوقة.")
    if note == "cooldown":
        lines.append("🔄 فرصة مكررة خلال فترة التهدئة؛ ممنوع اعتبارها دخول جديد.")
    elif note == "active_observation":
        lines.append("🔄 هناك إشارة سابقة قيد المتابعة، وهذه ليست صفقة إضافية.")
    elif note == "price_moved":
        lines.append("⚠️ السعر تحرك بعيدًا عن الدخول الأول؛ لا تطارد الإشارة.")
    lines += [
        f"🕒 {hour} {suffix} — توقيت فلسطين",
        "📄 رصد تعليمي فقط، بدون أوامر تداول أو ضمان ربح.",
    ]
    return "\n".join(lines)
