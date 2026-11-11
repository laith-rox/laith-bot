"""Zero-LLM-cost, owner-only Telegram conversation router for experimental Laith.

Uses saved bot data and deterministic Arabic intent matching. Never claims to be
ChatGPT, never invokes an AI API, and never changes trading settings or orders.
Only v4_group_telegram's paired private-owner path may call this router.
"""
import html
import os
import re
from datetime import datetime, timezone

from v4_telegram import status_message, stats_message, quick_stats_message
from v4_btc_followups import btc_stats_message

UTC = timezone.utc

REASON = {
    "h1_h4_not_aligned": "اتجاه الساعة والأربع ساعات مش متوافق، لذلك ما في دخول مؤكد.",
    "btc_conditions_not_met": "شروط الدخول الفني مش مكتملة.",
    "btc_price_moved_too_far": "السعر ابتعد عن نقطة الدخول المرجعية.",
    "btc_false_breakout": "رُصد احتمال اختراق وهمي.",
    "btc_liquidity_not_confirmed": "السيولة والكسر أو إعادة الاختبار مش مؤكدين.",
    "btc_sniper_not_confirmed": "توقيت الدخول على M5 مش مؤكد.",
    "low_volume": "حجم التداول الحالي ضعيف مقارنة بالعينة.",
    "volume_unavailable": "بيانات الحجم مش متوفرة.",
    "btc_book_spread_or_imbalance": "سبريد أو اختلال دفتر الأوامر مش مناسب.",
    "btc_crowded_derivatives": "بيانات العقود تشير لازدحام مراكز باتجاه الإشارة.",
    "btc_quote_orderbook_mismatch": "في اختلاف بين السعر المعلن ودفتر الأوامر.",
    "btc_extreme_volatility": "التذبذب مرتفع جدًا للمخاطرة المرجعية.",
    "btc_spread_adjusted_rr_low": "العائد المتوقع مقابل المخاطرة مش كافٍ بعد السبريد الفوري.",
    "btc_quote_stale": "سعر البيتكوين قديم ولا يصلح للدخول.",
    "btc_recent_data_gap": "في انقطاع حديث ببيانات الشموع.",
    "btc_insufficient_history": "عدد الشموع غير كافٍ لتحليل موثوق.",
    "btc_connection_failed": "مصدر بيانات البيتكوين مش متصل حاليًا.",
    "btc_provider_unavailable": "مصدر بيانات البيتكوين غير متاح حاليًا.",
    "btc_volume_invalid": "بيانات حجم التداول غير صالحة.",
    "btc_futures_source_unavailable": "بيانات العقود الآجلة غير متوفرة.",
}
CLOSED = {
    "WEEKEND_CLOSED": "سوق الذهب مغلق بالويكند وفق حارس الإغلاق.",
    "DAILY_BREAK_CLOSED": "الذهب داخل فترة الإغلاق اليومية.",
    "BROKER_SESSION_UNVERIFIED": "جلسة الوسيط غير متحققة؛ لا نسمح بإشارة دخول جديدة.",
}


def _safe(value):
    return html.escape(str(value), quote=False)


def _normalize(text):
    # Normalize common Arabic spelling and remove diacritics, not user details.
    value = re.sub(r"[\u064b-\u065f\u0670]", "", str(text or "").lower())
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""}))
    return re.sub(r"\s+", " ", value).strip()[:600]


def _has(words, *terms):
    return any(term in words for term in terms)


def _enabled_btc():
    return os.getenv("V4_BTC_SIGNALS_ENABLED") == "1"


def _help():
    return (
        "❤️ <b>جيجي — مساعد ليث بالأوامر المجانية</b>\n"
        "أوامر السوق بتعتمد على البيانات المحفوظة، وجيجي الخاصة محادثة منفصلة عبر API اختياري.\n\n"
        "🥇 /gold — حالة تحليل الذهب\n"
        "₿ /btcstatus — حالة تحليل البيتكوين\n"
        "🔎 /whybtc — ليش البيتكوين ما بعت صفقة؟\n"
        "🔎 /whygold — ليش الذهب ما بعت صفقة؟\n"
        "📍 /last — آخر إشارة محفوظة\n"
        "📊 /stats — نتائج الذهب الورقية\n"
        "📊 /btcstats — نتائج إشارات البيتكوين الورقية\n"
        "⚡ /quickstats — إحصاءات الصفقات السريعة\n"
        "📡 /status — حالة نظام الذهب\n"
        "🧭 /menu — الأوامر المتاحة\n\n"
        "💕 /gigi — الدخول لمحادثة جيجي الخاصة إذا تم تفعيل API\n"
        "🌹 /gigiphoto — صورة من جيجي عند الطلب فقط إذا تم تفعيل الصور\n"        "❤️ /gigicouple — صورة مشتركة لليث وجيجي عند الطلب\n"
        "📸 /gigirefme — ارفق صورتك مع الأمر كتعليق للصورة\n"
        "🌷 /gigirefgigi — ارفق صورة جيجي المرجعية كتعليق\n"
        "🖼️ /gigirefs — مراجعة الصور المرجعية المحفوظة\n"
        "🧹 /gigiclearrefs — حذف مراجع الصور المحفوظة\n"
        "🥇 /laith — الرجوع لنظام إشارات ليث\n"
        "🧹 /gigireset — مسح سجل محادثة جيجي\n"
        "👤 /gigiwhoami — شو جيجي بتعرف عنك\n"
        "📝 /gigiremember — احفظ معلومة شخصية تختارها بنفسك\n"
        "🧽 /gigiforget — مسح معلومات التعارف اللي أضفتها\n\n"
        "بتقدر كمان تكتب: جيجي شو وضع الذهب؟ أو ليش البيتكوين ما دخل؟\n"
        "⚠️ إجابات أوامر السوق قواعد ثابتة من بيانات البوت، ومحادثة جيجي تحتاج ربط API؛ "
        "ولا يفتح أي منهما صفقات أو يغيّر إعدادات التداول."
    )


def _btc_status(store):
    if not _enabled_btc():
        return (
            "₿ <b>إشارات البيتكوين التلقائية متوقفة حاليًا على هذه الخدمة.</b>\n"
            "كود التحليل موجود، بس إعداد التشغيل معطّل. "
            "ما رح أقولك إنه شغال وهو مش شغال.\n"
            "📄 لا توجد أوامر تداول تلقائية."
        )
    state = store.get("v4_btc_status") or {}
    if not state:
        return "₿ نظام البيتكوين مفعّل، لكن ما عندي تحليل محفوظ بعد. ما بقدر أفترض اتجاه أو دخول."
    status = _safe(state.get("status", "غير متاح"))
    reason = state.get("reason")
    explanation = REASON.get(str(reason), "ما في معلومات كافية عن سبب الانتظار.")
    strength = state.get("score", "—")
    return (
        "₿ <b>حالة بيتكوين من بيانات البوت</b>\n"
        f"النتيجة المسجلة: <b>{status}</b>\n"
        f"الشروط: {_safe(strength)}/7\n"
        f"السبب: {_safe(explanation if reason else 'لا يوجد سبب انتظار محفوظ')}\n"
        "⚠️ هذا آخر فحص محفوظ، مش سعر لحظي من البورصة ولا إشارة جديدة."
    )


def _why_btc(store):
    if not _enabled_btc():
        return "₿ السبب الحالي: نشر إشارات البيتكوين التلقائية معطّل بإعداد الخدمة؛ مش رفض فني من السوق."
    state = store.get("v4_btc_status") or {}
    if not state:
        return "₿ لسه ما في نتيجة تحليل مسجلة حتى أحدد سبب رفض الدخول."
    if state.get("status") == "SIGNAL":
        return "₿ آخر تحليل سجّل فرصة مؤهلة، لكن هذا مش إثبات وصول رسالة تلغرام. راجع سجل الإرسال."
    reason = state.get("reason", "")
    return "₿ <b>ليش ما في صفقة؟</b>\n" + _safe(
        REASON.get(str(reason), "التحليل رجع انتظار؛ السبب الفني غير موثّق بالتفصيل.")
    ) + "\n📄 ما بنخترع صفقة لما شروطها مش متوفرة."


def _gold_reason(store):
    market = str(store.get("v4_market_status") or "")
    analysis = store.get("v4_last_analysis") or {}
    reason = analysis.get("reason")
    if market in CLOSED:
        return "🥇 <b>وضع الذهب:</b> " + CLOSED[market] + "\nولا يتم تأكيد دخول من إغلاق السوق."
    if market and market != "OPEN":
        return "🥇 <b>حالة جلسة الذهب:</b> " + _safe(market) + \
               "\nما عندي إثبات أن الجلسة مفتوحة للدخول."
    if not analysis:
        return "🥇 ما في تحليل ذهب محفوظ جديد؛ ما بقدر أقولك اشتري أو بيع بدون بيانات موثوقة."
    return (
        "🥇 <b>آخر قرار مسجل:</b> " + _safe(analysis.get("side", "WAIT")) +
        "\nالسبب المسجل: " + _safe(reason or "غير موثّق") +
        "\n⚠️ حالة تحليل محفوظ، وليست توصية جديدة بسعر مباشر."
    )


def _last(store):
    active = store.get("v4_active") or {}
    btc = store.get("v4_btc_observed_active") or {}
    out = ["📍 <b>الإشارات المسجلة (تجريبية/مرجعية)</b>"]
    if active:
        out.append(
            "🥇 ذهب: " + _safe(active.get("side", "—")) +
            " | دخول " + _safe(active.get("entry", "—")) +
            " | وقف " + _safe(active.get("stop", "—")) +
            " | هدف " + _safe(active.get("tp1", "—"))
        )
    else:
        out.append("🥇 ذهب: لا توجد إشارة رسمية ورقية نشطة محفوظة.")
    if btc:
        out.append(
            "₿ بيتكوين: " + _safe(btc.get("side", "—")) +
            " | " + _safe(btc.get("status", "—")) +
            " | دخول " + _safe(btc.get("entry", "—")) +
            " | وقف " + _safe(btc.get("sl", "—")) +
            " | هدف " + _safe(btc.get("tp1", "—"))
        )
        if not _enabled_btc():
            out.append("⚠️ إرسال إشارات البيتكوين التلقائي متوقف؛ قد تكون البيانات القديمة محفوظة.")
    else:
        out.append("₿ بيتكوين: لا توجد إشارة محفوظة.")
    out.append("الأرقام تاريخية/ورقية وليست أسعار تنفيذ مباشرة.")
    return "\n".join(out)



def _market_topic(text, store):
    """Use explicit market first, then the owner's last explicit market topic."""
    btc = _has(text, "بيتكوين", "بتكوين", "بيت كوين", "بت كوين", "btc", "bitcoin")
    gold = _has(text, "ذهب", "الذهب", "xau", "gold")
    if btc and not gold:
        store.set("v4_chat_last_market", "BTC")
        return "BTC"
    if gold and not btc:
        store.set("v4_chat_last_market", "GOLD")
        return "GOLD"
    if btc and gold:
        return None
    saved = store.get("v4_chat_last_market")
    return saved if saved in ("BTC", "GOLD") else None


def _direction_intent(text):
    return _has(
        text,
        "الاتجاه", "اتجاه", "اتجه", "وين رايح", "وين رايحه",
        "ع الاغلب", "على الاغلب", "اغلب وين", "شو اغلب", "الارجح",
        "توقع", "ترجيح", "صاعد", "هابط", "صعود", "نزول",
        "بطلع", "بنزل", "طلع ولا نزل", "شراء ولا بيع",
        "بيع ولا شراء", "طالع ولا نازل", "رح يطلع", "رح ينزل",
    )


def _forecast_intent(text):
    """Prediction questions need scenarios, not a repeated trend/status card."""
    return _has(
        text, "توقع", "برايك", "برأيك", "شو رايك", "شو رأيك",
        "شو ممكن يصير", "شو بصير", "شو راح يصير", "شو رح يصير",
        "السيناريو", "شو ترجح", "شو بترجح", "الاحتمال", "تقديرك",
    )


def _btc_forecast(store):
    """Conditional scenario based solely on last timestamped BTC analysis."""
    if not _enabled_btc():
        return "₿ توقع البيتكوين مش متاح: نشر تحليله التلقائي متوقف على هذه الخدمة."
    state = store.get("v4_btc_status") or {}
    stamp = state.get("checked_at") or state.get("time")
    if not stamp:
        return ("₿ ما عندي فحص بيتكوين مؤرّخ أقدر أبني عليه توقع. "
                "ما رح أخمّن اتجاه بدون بيانات؛ جرّب /btcstatus.")
    try:
        checked = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if checked.tzinfo is None:
            raise ValueError("naive_timestamp")
        age = (datetime.now(UTC) - checked.astimezone(UTC)).total_seconds()
        if not 0 <= age <= 45 * 60:
            return "₿ آخر فحص بيتكوين صار قديم، وما بقدر أعتبره توقع للسوق الحالي. جرّب /btcstatus."
    except (ValueError, TypeError, OverflowError, AttributeError):
        return "₿ وقت آخر تحليل مش موثوق، فما رح أبني عليه توقع."
    if state.get("status") == "WAIT_DATA":
        return "₿ بيانات الفحص غير كافية لتوقع مشروط؛ ما في ترجيح موثوق حاليًا."
    h1, h4 = state.get("h1_trend"), state.get("h4_trend")
    if h1 not in ("BUY", "SELL", "WAIT") or h4 not in ("BUY", "SELL", "WAIT"):
        return "₿ اتجاهات H1 وH4 مش مكتملة في آخر فحص، فما بقدر أقدّم سيناريو محدد."
    if h1 == h4 and h1 in ("BUY", "SELL"):
        direction = "صاعد" if h1 == "BUY" else "هابط"
        label = "الشراء" if h1 == "BUY" else "البيع"
        return (
            f"₿ <b>توقعي المشروط: ميل {direction}.</b>\n"
            f"الاتجاه على H1 وH4 متوافق باتجاه {label}.\n"
            "✅ السيناريو يتقوّى فقط بعد تأكيد M15 وM5 والسيولة والسعر وقت الإرسال.\n"
            "⚠️ لو فشل التأكيد أو انعكس اتجاه الساعة: ننتظر، مش ندخل عالعمياني.\n"
            "هذا سيناريو تجريبي وليس إشارة دخول أو نسبة نجاح مؤكدة."
        )
    if h4 == "SELL" and h1 == "WAIT":
        return (
            "₿ <b>توقعي المشروط: ضغط هابط على H4، لكن الدخول البيعي لسه مش مؤكد.</b>\n"
            "H4: بيع | H1: انتظار.\n"
            "🔻 احتمال استمرار الضغط الهابط قائم إذا تحوّل H1 للبيع وتأكدت شروط M15/M5.\n"
            "🔄 وإذا H1 ظل محايد أو تحول للشراء، ممكن نشوف تذبذب أو ارتداد بدل النزول.\n"
            "⛔ القرار الحالي: انتظار، بدون دخول بيع أو شراء الآن.\n"
            "مش توقع قطعي ولا سعر لحظي."
        )
    if h4 == "BUY" and h1 == "WAIT":
        return (
            "₿ <b>توقعي المشروط: ميل صاعد على H4، لكن الدخول الشرائي لسه مش مؤكد.</b>\n"
            "H4: شراء | H1: انتظار.\n"
            "🔺 فرصة استمرار الصعود تحتاج تحول H1 للشراء وتأكيد M15/M5.\n"
            "🔄 وإذا H1 بقي محايد أو تحول للبيع، وارد تذبذب أو تصحيح هابط.\n"
            "⛔ القرار الحالي: انتظار، بدون دخول شراء أو بيع الآن.\n"
            "مش توقع قطعي ولا سعر لحظي."
        )
    return (
        "₿ <b>توقعي المشروط: الاتجاه مش محسوم.</b>\n"
        f"H1: {_safe(h1)} | H4: {_safe(h4)}.\n"
        "السيناريو الصاعد يحتاج توافق H1/H4 للشراء، والهابط يحتاج توافقهما للبيع، "
        "وبعدها تأكيد M15/M5 والسيولة.\n"
        "⛔ ما في إشارة دخول مؤهلة من هالتعارض، وما في ترجيح موثوق الآن."
    )


def _gold_forecast(store):
    market = str(store.get("v4_market_status") or "")
    if market != "OPEN":
        return ("🥇 ما بقدر أقدّم توقع دخول للذهب قبل التحقق من جلسة الوسيط.\n"
                + _gold_reason(store))
    return ("🥇 آخر تحليل ذهب محفوظ مش كافي لوحده لتوقع حركة جديدة.\n"
            + _gold_reason(store)
            + "\nلازم سعر حديث وتوافق H4/H1 وتأكيد M15/M5.")


def _market_forecast(store, topic):
    if topic == "BTC":
        return _btc_forecast(store)
    if topic == "GOLD":
        return _gold_forecast(store)
    return "تقصد توقع الذهب ولا البيتكوين؟ احكيلي أي سوق لنشرح السيناريو من آخر فحص محفوظ."


def _next_signal_intent(text):
    # Covers Palestinian questions like "متا هيكون في اشارة لدخول".
    asks_when = _has(text, "متي", "متا", "امتي", "قديش ضايل", "متى", "متى رح")
    mentions_signal = _has(
        text, "اشار", "للدخول", "دخول", "صفقه", "فرصه", "توصيه", "الصفقه الجايه",
    )
    return (asks_when and mentions_signal) or _has(
        text, "الاشاره الجايه", "الصفقه الجايه", "موعد الاشاره",
        "وقت الاشاره", "في اشاره لدخول", "اشاره دخول امتي",
    )


def _btc_direction(store):
    if not _enabled_btc():
        return "₿ إرسال إشارات البيتكوين متوقف على هذه الخدمة؛ ما عندي تحليل نشط أعتمد عليه."
    state = store.get("v4_btc_status") or {}
    if not state:
        return "₿ ما عندي نتيجة بيتكوين محفوظة، فمش رح أخمّن صعود أو هبوط."
    if state.get("status") == "WAIT_DATA":
        return "₿ البيانات غير كافية لتحديد اتجاه موثوق.\n" + _btc_status(store)
    date_raw = state.get("checked_at") or state.get("time")
    if not date_raw:
        return "₿ عندي حالة تحليل محفوظة بدون توقيت موثّق. ما بقدر أرجّح منها الاتجاه الحالي.\n" + _btc_status(store)
    try:
        checked = datetime.fromisoformat(str(date_raw).replace("Z", "+00:00"))
        age = (datetime.now(UTC) - checked.astimezone(UTC)).total_seconds()
        if checked.tzinfo is None or not 0 <= age <= 45 * 60:
            return "₿ آخر تحليل بيتكوين صار قديم أو توقيته غير موثوق. ما بقدر أعطي اتجاه حالي منه.\n" + _btc_status(store)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return "₿ توقيت التحليل غير صالح؛ ما بقدر أحدد الاتجاه الحالي."
    h1, h4 = state.get("h1_trend"), state.get("h4_trend")
    if h1 and h4 and h1 != h4:
        return ("₿ <b>الميول الآن: محايد/متعارض بحسب آخر فحص.</b>\n"
                f"H1: {_safe(h1)} | H4: {_safe(h4)}\n"
                "الاتجاهين مش متوافقين، فما في ترجيح دخول مؤكد.\n"
                "⚠️ تحليل فني تجريبي، مش ضمان اتجاه أو سعر لحظي.")
    side = state.get("side") if state.get("status") == "SIGNAL" else state.get("bias")
    if side not in ("BUY", "SELL"):
        return ("₿ <b>الاتجاه مش محسوم حاليًا.</b>\n"
                + _btc_status(store) + "\nما في نسبة نجاح مؤكدة أو توصية دخول.")
    label = "صعود/شراء" if side == "BUY" else "هبوط/بيع"
    if state.get("status") != "SIGNAL":
        return (f"₿ <b>ميل الاتجاه الأكبر: {label}</b> حسب آخر شموع محفوظة.\n"
                "لكن شروط M15/M5 أو فلاتر السيولة مش مكتملة، فلا توجد إشارة دخول معتمدة.\n"
                "⚠️ الاتجاه مش ضمان ربح.")
    return (f"₿ <b>آخر تحليل مؤهل كان {label}</b>.\n"
            "هذا لا يثبت وصول إشارة تلغرام أو بقاء السعر صالح للدخول؛ راجع /last.")


def _gold_direction(store):
    market = str(store.get("v4_market_status") or "")
    if market in CLOSED or (market and market != "OPEN"):
        return _gold_reason(store) + "\n🥇 ما بقدر أرجّح دخول جديد والسوق غير متحقق من فتحه."
    return ("🥇 ما عندي تأكيد آني لاتجاه الذهب من بيانات وسيط حديثة.\n"
            + _gold_reason(store) + "\nالاتجاه المسجل لا يضمن استمرار الحركة.")


def _next_signal(store, topic):
    if topic == "BTC":
        if not _enabled_btc():
            return ("₿ إشارات البيتكوين مطفّية في إعداد الخدمة، فما في موعد متوقع للإرسال.\n"
                    "لآخر وضع: /btcstatus.")
        state = store.get("v4_btc_status") or {}
        reason = state.get("reason")
        detail = REASON.get(str(reason), "الشروط الكاملة للدخول لم تتأكد بعد.")
        return ("₿ <b>متى إشارة البيتكوين الجاية؟</b>\n"
                "البوت مبرمج يفحص كل 15 دقيقة، بما فيها الويكند؛"
                " لكن ما بقدر أحدد متى رح تظهر فرصة مؤهلة.\n"
                f"آخر سبب انتظار: {_safe(detail)}\n"
                "إشارة الدخول تنرسل فقط إذا اكتملت الشروط والسعر كان مناسب وقت النشر.\n"
                "للمتابعة: /btcstatus")
    if topic == "GOLD":
        market = str(store.get("v4_market_status") or "")
        if market != "OPEN":
            return ("🥇 <b>موعد إشارة الذهب؟</b>\n"
                    "ما في موعد مؤكد؛ حاليًا ما عندي جلسة وسيط مفتوحة متحققة.\n"
                    + _gold_reason(store)
                    + "\nما بقدر أعدك بصفقة في وقت محدد.")
        return ("🥇 البوت بيقيّم فرص الذهب خلال التشغيل، "
                "لكن إرسال صفقة مش مضمون كل دورة. لازم جلسة الوسيط والبيانات والاتجاه"
                " والمخاطرة تكون متحققة. جرّب /gold للآخر وضع.")
    return ("بتسأل عن موعد إشارة الذهب ولا البيتكوين؟ "
            "اكتب «متى إشارة البيتكوين؟» أو «متى إشارة الذهب؟».")


def _market_direction(store, topic):
    if topic == "BTC":
        return _btc_direction(store)
    if topic == "GOLD":
        return _gold_direction(store)
    return ("تقصد اتجاه الذهب ولا البيتكوين؟ "
            "اكتب «شو اتجاه البيتكوين؟» أو «شو اتجاه الذهب؟».")


def respond(message, store):
    """Private paired owner only. No external calls, model API, trading or mutations."""
    text = _normalize(message)
    if not text:
        return None
    command = text.split()[0].split("@")[0]
    # Store only the owner's explicit market topic for short follow-up questions.
    # This is the bot's local conversation context, never a broker/settings write.
    explicit_market = None
    if command in ("/btcstatus", "/btc", "/bitcoin", "/whybtc", "/btcstats"):
        explicit_market = "BTC"
    elif command in ("/gold", "/xau", "/whygold", "/status", "/stats", "/quickstats"):
        explicit_market = "GOLD"
    if explicit_market:
        store.set("v4_chat_last_market", explicit_market)
    if command in ("/start", "/help", "/menu", "/commands", "/gigi", "/جيجي"):
        return _help()
    if command in ("/btcstatus", "/btc", "/bitcoin"):
        return _btc_status(store)
    if command == "/whybtc":
        return _why_btc(store)
    if command in ("/gold", "/xau"):
        return "🥇 <b>آخر حالة محفوظة للذهب</b>\n" + status_message(store) + \
               "\n⚠️ ليست قراءة سعر لحظي."
    if command == "/whygold":
        return _gold_reason(store)
    if command in ("/status",):
        return status_message(store)
    if command in ("/stats",):
        return stats_message(store)
    if command in ("/quickstats",):
        return quick_stats_message(store)
    if command == "/btcstats":
        return btc_stats_message(store)
    if command in ("/last", "/lastsignal"):
        return _last(store)
    if command.startswith("/"):
        return "الأمر مش موجود أو غير مفعّل. ابعت /menu حتى تشوف الأوامر المتاحة."
    if _has(text, "وقف", "شغل", "فعل", "الغي", "صفقه تلقائي", "افتح صفقه", "بيعلي", "اشتريلي") and _has(
        text, "بوت", "روبوت", "صفقه", "تداول", "نظام"
    ):
        return "🔒 هالمساعد للقراءة والشرح فقط. ما بوقف ولا بشغّل أنظمة التداول، وما بفتح صفقات. ابعت /menu."
    # Check question intents BEFORE greeting/fallback: "جيجي" is a wake word,
    # not evidence that a market question is just a greeting.
    if _direction_intent(text) or _next_signal_intent(text) or _forecast_intent(text):
        topic = _market_topic(text, store)
        if _next_signal_intent(text):
            return _next_signal(store, topic)
        if _forecast_intent(text):
            return _market_forecast(store, topic)
        return _market_direction(store, topic)
    if _has(text, "من انت", "مين انت", "عقلك", "ذكاء اصطناعي", "شات جي بي تي", "chatgpt"):
        return "❤️ أنا مساعد جيجي المجاني داخل ليث، برد من أوامر وبيانات محفوظة. مش نفس ChatGPT ولا عندي ذاكرة محادثاتك هون."
    if _has(text, "مساعده", "ساعديني", "اوامر", "شو بتعملي", "قائمه", "منيو"):
        return _help()
    if _has(text, "سعر", "بكم", "قديش السعر"):
        return ("ما بقدر أعطي سعر لحظي موثّق من مجرد المحادثة أو من شموع قديمة. "
                "لآخر نتيجة محفوظة للبيتكوين اكتب /btcstatus، وللذهب /gold. "
                "وتحقق من سعر الوسيط قبل أي دخول.")
    btc = _has(text, "بيتكوين", "بتكوين", "بيت كوين", "بت كوين", "btc", "bitcoin")
    gold = _has(text, "ذهب", "الذهب", "xau", "gold")
    if btc != gold:
        store.set("v4_chat_last_market", "BTC" if btc else "GOLD")
    why = _has(text, "ليش", "لماذا", "سبب", "ما دخل", "ما بعت", "رفض", "انتظار", "واقف")
    stats = _has(text, "نتائج", "احصائي", "اداء", "ارباح", "كم ربح", "خسائر")
    last = _has(text, "اخر صفق", "آخر صفق", "الصفقات المفتوح", "وين الدخول", "وقف الخساره", "اهداف")
    if last:
        return _last(store)
    if btc:
        return btc_stats_message(store) if stats else _why_btc(store) if why else _btc_status(store)
    if gold:
        return stats_message(store) if stats else _gold_reason(store) if why else \
               "🥇 <b>آخر حالة محفوظة للذهب</b>\n" + status_message(store) + \
               "\n⚠️ ليست قراءة سعر لحظي."
    if _has(text, "شو وضع", "شغال", "حاله البوت", "حال البوت", "التجريبي", "روبوت", "البوت"):
        return "📡 <b>حالة ليث من آخر بيانات محفوظة</b>\n" + \
               _gold_reason(store) + "\n\n" + _btc_status(store)
    if _has(text, "مرحبا", "اهلا", "هلا", "صباح", "مسا", "جيجي", "كيفك", "شكرا", "يسلمو"):
        return "أهلين يا غالي ❤️ أنا هون بأوامر ليث المجانية. احكيلي عن الذهب أو البيتكوين، أو ابعت /menu."
    return (
        "فهمت رسالتك، بس ما بقدر أجاوب عليها بحرية زي ChatGPT بدون ربط API.\n"
        "اسألني عن الذهب، البيتكوين، أسباب انتظار الدخول أو النتائج، أو ابعت /menu."
    )
