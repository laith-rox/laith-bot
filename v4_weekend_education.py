"""Weekend-only educational stream for Laith V4.

The stream is intentionally offline: it never requests live market data and never
creates or saves a tradable signal. It alternates between a completed profitable
paper trade from V4's own journal and a clearly marked hypothetical example.
"""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")


def weekend_education_window(now):
    """Saturday through the regular Sunday gold/FX reopen, in New York time."""
    local = now.astimezone(NY_TZ)
    weekday = local.weekday()  # Mon=0 ... Sun=6
    if weekday == 5:
        return True
    if weekday == 6 and local.hour < 18:
        return True
    return False


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _price(value):
    number = _number(value)
    return "—" if number is None else f"{number:.2f}"


def _side_ar(side):
    return "شراء BUY" if side == "BUY" else "بيع SELL" if side == "SELL" else str(side or "—")


def _successful_trades(paper):
    rows = []
    for reader in ("_paper_rows", "_quick_rows"):
        fn = getattr(paper, reader, None)
        if not callable(fn):
            continue
        try:
            rows.extend(fn() or [])
        except Exception:
            continue
    winners = []
    for trade in rows:
        r_value = _number(trade.get("r"))
        if trade.get("status") == "closed" and r_value is not None and r_value > 0:
            winners.append(trade)
    winners.sort(
        key=lambda trade: _number(trade.get("closed"))
        or _number(trade.get("announced"))
        or _number(trade.get("created"))
        or 0.0
    )
    return winners


def _historical_reasons(trade):
    reasons = []
    side = trade.get("side")
    score = trade.get("score", trade.get("signal_score"))
    total = trade.get("signal_total", 7)
    if score is not None:
        reasons.append(f"تأكيد الشروط كان {score}/{total} قبل الدخول.")

    conditions = trade.get("conditions") or []
    passed = [str(item.get("name")) for item in conditions if isinstance(item, dict) and item.get("ok")]
    if passed:
        reasons.append("من الشروط التي تحققت: " + "، ".join(passed[:3]) + ".")

    research = trade.get("research_v4") or {}
    breakout = research.get("breakout_state") or trade.get("breakout_state")
    if breakout:
        reasons.append(f"حالة الاختراق وقتها كانت: {breakout}.")

    correction = research.get("correction") or {}
    corr_direction = correction.get("direction")
    corr_strength = correction.get("strength")
    if corr_direction or corr_strength:
        reasons.append(
            "التصحيح كان مراقَبًا"
            + (f" باتجاه {corr_direction}" if corr_direction else "")
            + (f" وبقوة {corr_strength}" if corr_strength else "")
            + "."
        )

    support = research.get("nearest_support") or {}
    resistance = research.get("nearest_resistance") or {}
    support_price = _number(support.get("center"))
    resistance_price = _number(resistance.get("center"))
    if side == "BUY" and support_price is not None:
        reasons.append(f"كان هناك دعم قريب حول {support_price:.2f} يساعد فكرة الشراء.")
    if side == "SELL" and resistance_price is not None:
        reasons.append(f"كانت هناك مقاومة قريبة حول {resistance_price:.2f} تساعد فكرة البيع.")

    if not reasons:
        reasons.append("الصفقة أُخذت بعد اكتمال شروط V4 وقتها، وليس بسبب حركة شمعة واحدة.")
    return reasons[:4]


def _historical_message(trade):
    side = trade.get("side")
    entry = trade.get("entry")
    stop = trade.get("stop")
    target = trade.get("target", trade.get("tp1"))
    r_value = _number(trade.get("r"))
    reasons = _historical_reasons(trade)

    if side == "BUY":
        diagnosis = (
            "التشخيص الصحيح للشراء: اتجاه عام غير هابط بقوة، دعم واضح أو إعادة اختبار ناجحة، "
            "ثم تأكيد من شمعة/شروط 5د قبل الدخول."
        )
        invalidation = "لو كُسر الدعم أو مستوى الإبطال بوضوح، فكرة الشراء تنتهي ولا نطارد السعر."
    else:
        diagnosis = (
            "التشخيص الصحيح للبيع: اتجاه عام غير صاعد بقوة، مقاومة واضحة أو إعادة اختبار فاشلة، "
            "ثم تأكيد هابط من شمعة/شروط 5د قبل الدخول."
        )
        invalidation = "لو اختُرقت المقاومة أو مستوى الإبطال بوضوح، فكرة البيع تنتهي ولا نطارد السعر."

    bullets = "\n".join(f"• {reason}" for reason in reasons)
    return (
        "📘 صفقة تعليمية — من سجل Laith V4\n"
        "⚠️ ليست إشارة دخول الآن؛ السوق مغلق وهذه مراجعة لصفقة ورقية سابقة انتهت بالربح.\n\n"
        f"الاتجاه: {_side_ar(side)}\n"
        f"الدخول السابق: {_price(entry)}\n"
        f"وقف الخسارة: {_price(stop)}\n"
        f"الهدف: {_price(target)}\n"
        f"النتيجة المسجلة: {r_value:+.2f}R\n\n"
        "لماذا كانت الفكرة جيدة وقتها؟\n"
        f"{bullets}\n\n"
        "كيف تشخّص صفقة مشابهة؟\n"
        f"1) {diagnosis}\n"
        "2) حدّد الدعم والمقاومة قبل الضغط على شراء/بيع.\n"
        "3) انتظر التأكيد؛ لا تدخل فقط لأن السعر لمس مستوى.\n"
        f"4) {invalidation}\n"
        "5) اجعل الوقف عند الإبطال الحقيقي، والهدف قبل العائق المقابل.\n\n"
        "🧠 الهدف من الرسالة: تتعلم لماذا دخل البوت، لا أن تقلّد الرقم بعد انتهاء الصفقة."
    )


EXAMPLES = (
    {
        "title": "شراء من تصحيح داخل اتجاه صاعد",
        "side": "شراء BUY",
        "entry": "4300.00 بعد شمعة تأكيد صاعدة",
        "stop": "4293.00 تحت الدعم/الإبطال",
        "target": "4314.00 قرب المقاومة التالية",
        "why": (
            "الاتجاه الأكبر صاعد، السعر رجع إلى دعم بدل مطاردة القمة، "
            "ثم ظهر رفض هابط ضعيف وتأكيد صاعد على 5د."
        ),
        "checks": (
            "حدّد اتجاه M15/H1 أولًا.",
            "انتظر وصول السعر لمنطقة دعم، لا تدخل في منتصف الحركة.",
            "ادخل فقط بعد تأكيد صاعد، والوقف تحت الإبطال.",
        ),
    },
    {
        "title": "بيع من مقاومة داخل اتجاه هابط",
        "side": "بيع SELL",
        "entry": "4300.00 بعد رفض واضح للمقاومة",
        "stop": "4307.00 فوق المقاومة/الإبطال",
        "target": "4286.00 قبل الدعم التالي",
        "why": (
            "الاتجاه الأكبر هابط، الصعود كان تصحيحًا نحو مقاومة، "
            "ثم فشل السعر في الثبات فوقها وظهر تأكيد هابط."
        ),
        "checks": (
            "فرّق بين الصعود التصحيحي وانعكاس الاتجاه.",
            "راقب هل المقاومة ما زالت صامدة بعد إعادة الاختبار.",
            "لا تبيع لمجرد شمعة حمراء؛ انتظر تأكيدًا وهيكلًا واضحًا.",
        ),
    },
    {
        "title": "شراء بعد اختراق وإعادة اختبار",
        "side": "شراء BUY",
        "entry": "4305.00 بعد إعادة اختبار ناجحة",
        "stop": "4298.00 أسفل مستوى الاختراق",
        "target": "4319.00",
        "why": (
            "المقاومة كُسرت ثم تحولت إلى دعم، وإعادة الاختبار حافظت على المستوى؛ "
            "هذا أقوى من الشراء أثناء لحظة الاختراق نفسها."
        ),
        "checks": (
            "اطلب إغلاقًا واضحًا فوق المقاومة.",
            "انتظر إعادة الاختبار بدل مطاردة شمعة الاختراق.",
            "إذا عاد السعر وثبت تحت المستوى فالإشارة تُلغى.",
        ),
    },
    {
        "title": "بيع بعد كسر وإعادة اختبار",
        "side": "بيع SELL",
        "entry": "4295.00 بعد إعادة اختبار فاشلة من الأسفل",
        "stop": "4302.00 فوق مستوى الكسر",
        "target": "4281.00",
        "why": (
            "الدعم كُسر ثم صار مقاومة، والسعر فشل في الرجوع فوقه؛ "
            "الدخول بعد إعادة الاختبار أوضح من البيع المتأخر في أسفل الحركة."
        ),
        "checks": (
            "اطلب كسرًا حقيقيًا لا مجرد ذيل شمعة.",
            "راقب إعادة الاختبار من الأسفل.",
            "إذا استعاد السعر المستوى وثبت فوقه ففكرة البيع انتهت.",
        ),
    },
    {
        "title": "اختراق كاذب — الأفضل عدم الدخول",
        "side": "انتظار WAIT",
        "entry": "لا دخول",
        "stop": "—",
        "target": "—",
        "why": (
            "السعر تجاوز المقاومة لحظيًا ثم عاد تحتها بسرعة؛ الدخول هنا قد يعني شراء قمة "
            "قبل انعكاس قصير."
        ),
        "checks": (
            "لا تعتبر الذيل اختراقًا مؤكدًا.",
            "اطلب إغلاقًا وثباتًا أو إعادة اختبار ناجحة.",
            "الانتظار صفقة بحد ذاته عندما يكون الإبطال غير واضح.",
        ),
    },
    {
        "title": "كيف تفرّق بين التصحيح والانعكاس",
        "side": "مثال تشخيصي",
        "entry": "بعد انتهاء التصحيح وعودة التأكيد مع الاتجاه",
        "stop": "خلف آخر قاع/قمة تبطل الفكرة",
        "target": "قبل المستوى المقابل التالي",
        "why": (
            "التصحيح غالبًا يحافظ على بنية الاتجاه الأكبر؛ الانعكاس يبدأ عندما تُكسر البنية "
            "وتتحول القمم والقيعان لصالح الاتجاه المعاكس."
        ),
        "checks": (
            "راقب القمم والقيعان لا لون شمعة واحدة.",
            "قارن M5 مع M15/H1.",
            "إذا كُسر مستوى بنيوي مهم، لا تسمِّ الحركة مجرد تصحيح.",
        ),
    },
)


def _example_message(slot):
    example = EXAMPLES[slot % len(EXAMPLES)]
    checks = "\n".join(f"{i}) {text}" for i, text in enumerate(example["checks"], 1))
    return (
        "📘 صفقة تعليمية — مثال افتراضي\n"
        "⚠️ ليست إشارة دخول، والأرقام للتدريب فقط لأن السوق مغلق.\n\n"
        f"المثال: {example['title']}\n"
        f"الاتجاه: {example['side']}\n"
        f"الدخول التعليمي: {example['entry']}\n"
        f"وقف الخسارة التعليمي: {example['stop']}\n"
        f"الهدف التعليمي: {example['target']}\n\n"
        f"لماذا؟ {example['why']}\n\n"
        "كيف نحللها؟\n"
        f"{checks}\n\n"
        "🧠 القاعدة: الاتجاه + المستوى + التأكيد + الإبطال، وليس الدخول من رقم عشوائي."
    )


def build_weekend_education_message(paper, now):
    """Alternate real completed winners with hypothetical teaching examples."""
    slot = int(now.timestamp() // 3600)
    winners = _successful_trades(paper)
    if winners and slot % 2 == 0:
        trade = winners[(slot // 2) % len(winners)]
        return _historical_message(trade)
    return _example_message(slot)


def maybe_send_weekend_education(store, notifier, paper, now):
    """Send at most one educational message per UTC hour during the weekend window."""
    if notifier is None or not weekend_education_window(now):
        return False
    slot = int(now.timestamp() // 3600)
    if store.get("v4_weekend_education_slot") == slot:
        return False
    message = build_weekend_education_message(paper, now)
    notifier.send(message)
    store.set("v4_weekend_education_slot", slot)
    store.set("v4_weekend_education_last_sent", now.isoformat())
    return True
