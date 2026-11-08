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
        # No timeframe has unilateral veto/power over a research hypothesis.
        # Tally symmetric BUY vs SELL evidence; inactive/neutral checks abstain.
        # The 7 slots are H4, H1, M15 EMA, M15 candle, M5 candle,
        # M5 RSI and completed M15 breakout. Counts are NOT probabilities.
        last15, last5 = m15[-1], bars[-1]
        rsi5 = rsi([b.close for b in bars[-70:]])
        recent = m15[-9:-1]
        upper = max(b.high for b in recent)
        lower = min(b.low for b in recent)
        def compare(a, b):
            return "BUY" if a > b else "SELL" if a < b else "WAIT"
        rsi_side = "BUY" if rsi5 >= 55 else "SELL" if rsi5 <= 45 else "WAIT"
        breakout_side = ("BUY" if last15.close > upper
                         else "SELL" if last15.close < lower else "WAIT")
        votes = [
            h4 if h4 in ("BUY", "SELL") else "WAIT",
            h1 if h1 in ("BUY", "SELL") else "WAIT",
            compare(fast, slow),
            compare(last15.close, last15.open),
            compare(last5.close, last5.open),
            rsi_side, breakout_side,
        ]
        buy = votes.count("BUY")
        sell = votes.count("SELL")
        # Require a clear 2-vote lead and 3 supporting observations.
        # Neither BUY nor SELL is forced when the evidence is tied/thin.
        side = ("BUY" if buy >= 3 and buy - sell >= 2 else
                "SELL" if sell >= 3 and sell - buy >= 2 else "WAIT")
        conflict = side in ("BUY", "SELL") and h4 in ("BUY", "SELL") and side != h4
        result = {
            "side": side, "score": (buy if side == "BUY" else sell if side == "SELL" else max(buy, sell)),
            "buy_votes": buy, "sell_votes": sell,
            "h4_conflict": bool(conflict),
            "m15_trend": votes[2], "m5_momentum": votes[5],
            "price": None, "sl": None, "tp1": None, "tp2": None,
        }
        if side == "WAIT":
            # Explicit neutral research outcome: no one-sided trade geometry.
            result["reason"] = "mixed_or_insufficient_votes"
            return result
        up = side == "BUY"
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
        f"⚖️ تصويت 7 عوامل: شراء {preview.get('buy_votes', '—')}/7 | بيع {preview.get('sell_votes', '—')}/7",
        f"🕓 H1: {_trend_label(state.get('h1_trend'))} | H4: {_trend_label(state.get('h4_trend'))}",
        f"📊 اتجاه M15: {_trend_label(preview.get('m15_trend'))} | زخم RSI M5: {_trend_label(preview.get('m5_momentum'))}",
        f"🟡 سبب عدم الدخول: {reason}",
    ]
    if preview.get("h4_conflict"):
        lines.append("⚠️ الميل المقترح عكس H4؛ احتمال تصحيح قصير، وليس انعكاسًا مؤكدًا. لا تدخل.")
    if preview.get("side") == "WAIT" and preview.get("reason") == "mixed_or_insufficient_votes":
        lines.append("⚪ لا توجد أغلبية كافية بين الشراء والبيع؛ لا نفرض صفقة افتراضية باتجاه واحد.")
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
