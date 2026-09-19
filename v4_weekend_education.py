"""Weekend-only educational stream for Laith V4.

# Arabic visual lesson release trigger

The stream is intentionally offline: it never requests live market data and never
creates or saves a tradable signal. It alternates between a completed profitable
paper trade from V4's own journal and a clearly marked hypothetical example.
"""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

from v4_global_academy import academy_message, academy_parts, curriculum_size
from v4_education_visuals import render_lesson_visual

NY_TZ = ZoneInfo("America/New_York")
LOCAL_TZ = ZoneInfo("Asia/Hebron")


INTENSIVE_LOCAL_DATE = (2026, 9, 19)


def tonight_intensive_window(now):
    """One-off intensive study mode for Laith until local midnight tonight."""
    local = now.astimezone(LOCAL_TZ)
    return (
        (local.year, local.month, local.day) == INTENSIVE_LOCAL_DATE
        and local.hour == 23
    )


def _between_lesson_cooldown(now):
    """Five minutes tonight before midnight, otherwise the normal one hour."""
    return 300 if tonight_intensive_window(now) else 3600


def weekend_education_window(now):
    """From local Saturday 00:00 until the regular Sunday 18:00 New York reopen."""
    local = now.astimezone(LOCAL_TZ)
    ny = now.astimezone(NY_TZ)

    # Laith's local weekend starts at 00:00 Saturday. Around DST changes the
    # Sunday New York reopen can fall after local midnight, so keep teaching
    # active into early Monday only while New York is still before 18:00 Sunday.
    if local.weekday() in (5, 6):
        return True
    if local.weekday() == 0 and ny.weekday() == 6 and ny.hour < 18:
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
    return "شراء" if side == "BUY" else "بيع" if side == "SELL" else str(side or "—")


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
    breakout_labels = {
        "BREAKOUT_UP": "اختراق صاعد",
        "BREAKOUT_DOWN": "اختراق هابط",
        "FAILED_BREAK": "اختراق فاشل",
        "NO_BREAK": "بدون اختراق مؤكد",
    }
    if breakout:
        reasons.append(f"حالة الاختراق وقتها كانت: {breakout_labels.get(breakout, breakout)}.")

    correction = research.get("correction") or {}
    corr_direction = correction.get("direction")
    corr_strength = correction.get("strength")
    direction_labels = {"UP": "صاعد", "DOWN": "هابط"}
    strength_labels = {"STRONG": "قوية", "MEDIUM": "متوسطة", "WEAK": "ضعيفة"}
    if corr_direction or corr_strength:
        reasons.append(
            "التصحيح كان مراقَبًا"
            + (f" باتجاه {direction_labels.get(corr_direction, corr_direction)}" if corr_direction else "")
            + (f" وبقوة {strength_labels.get(corr_strength, corr_strength)}" if corr_strength else "")
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
    research = trade.get("research_v4") or {}
    session = research.get("session") or trade.get("session") or "—"
    volatility = research.get("volatility_regime") or trade.get("volatility_regime") or "—"
    macro = research.get("macro_alignment") or trade.get("macro_alignment") or "—"

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
        f"النتيجة المسجلة: {r_value:+.2f}R\n"
        f"سياق الجلسة: {session} | نظام التقلب: {volatility} | توافق الماكرو: {macro}\n\n"
        "لماذا كانت الفكرة جيدة وقتها؟\n"
        f"{bullets}\n\n"
        "كيف تشخّص صفقة مشابهة؟\n"
        f"1) {diagnosis}\n"
        "2) حدّد الدعم والمقاومة قبل الضغط على شراء/بيع.\n"
        "3) انتظر التأكيد؛ لا تدخل فقط لأن السعر لمس مستوى.\n"
        f"4) {invalidation}\n"
        "5) اجعل الوقف عند الإبطال الحقيقي، والهدف قبل العائق المقابل.\n\n"
        "🧠 سؤال المحترف: هل كانت النتيجة بسبب جودة العملية أم الحظ؟ "
        "قارنها دائمًا بخاسر مشابه وحالة WAIT حتى لا تتعلم من الرابحين فقط.\n"
        "🎯 الهدف: تتعلم لماذا دخل البوت، لا أن تقلّد الرقم بعد انتهاء الصفقة."
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
    """Rotate real V4 case studies, research lessons and scenario drills."""
    slot = int(now.timestamp() // 3600)
    winners = _successful_trades(paper)
    mode = slot % 4

    # One real completed V4 winner every four lessons when history exists.
    if winners and mode == 0:
        trade = winners[(slot // 4) % len(winners)]
        return _historical_message(trade)

    # Two evidence-based research lessons out of every four messages.
    if mode in (1, 3):
        return academy_message(slot)

    # The remaining message is a concrete chart-reading scenario drill.
    return _example_message(slot)



def _historical_parts(trade, lesson_number):
    reasons = _historical_reasons(trade)
    research = trade.get("research_v4") or {}
    side = trade.get("side")
    entry = trade.get("entry")
    stop = trade.get("stop")
    target = trade.get("target", trade.get("tp1"))
    r_value = _number(trade.get("r"))
    return [
        {
            "text": (
                f"📊 <b>الدرس {lesson_number} — تشريح صفقة V4 حقيقية</b>\n"
                "هذه مراجعة لصفقة ورقية سابقة انتهت، وليست إشارة دخول الآن.\n\n"
                f"الاتجاه: {_side_ar(side)} | النتيجة: {r_value:+.2f}R"
            ),
        },
        {
            "text": (
                "🖼️ <b>الجزء 2 — خريطة الصفقة</b>\n\n"
                f"الدخول: {_price(entry)}\n"
                f"الوقف: {_price(stop)}\n"
                f"الهدف: {_price(target)}\n"
                f"الجلسة: {research.get('session', '—')} | التقلب: {research.get('volatility_regime', '—')}"
            ),
            "visual": "trend" if side == "BUY" else "structure",
            "visual_variant": 0,
            "visual_title": "REAL V4 CASE",
        },
        {
            "text": (
                "🔎 <b>الجزء 3 — لماذا دخل البوت؟</b>\n\n"
                + "\n".join(f"• {reason}" for reason in reasons)
            ),
        },
        {
            "text": (
                "🚫 <b>الجزء 4 — ماذا كان سيبطل الصفقة؟</b>\n\n"
                "الدخول الصحيح لا يكتمل بدون جواب واضح لسؤال: أين تصبح الفكرة خاطئة؟ "
                "لو كُسرت البنية التي بُنيت عليها الصفقة، لا نحول الخسارة إلى أمل."
            ),
            "visual": "process",
            "visual_variant": 1,
            "visual_title": "INVALIDATION",
        },
        {
            "text": (
                "🧪 <b>الجزء 5 — تدريبك</b>\n\n"
                "اكتب قبل أن ترى النتيجة: ما السياق؟ ما المستوى؟ ما التفعيل؟ ما الإبطال؟ "
                "ثم قارن جوابك بما فعله V4. الهدف أن تتعلم العملية، لا أن تقلّد الأرقام."
            ),
        },
        {
            "text": (
                f"✅ <b>انتهى الدرس {lesson_number}</b>\n\n"
                "⏳ <b>انتظر الدرس التالي بعد ساعة لتصبح متداولًا أنجح.</b>\n"
                "تذكّر: الصفقة الجيدة قد تخسر، لكن التفكير الجيد هو الذي يبني الاستمرارية."
            ),
        },
    ]


def _example_parts(slot, lesson_number):
    example = EXAMPLES[slot % len(EXAMPLES)]
    return [
        {
            "text": (
                f"📘 <b>الدرس {lesson_number} — سيناريو تطبيقي</b>\n"
                f"🎓 {example['title']}\n\n"
                "الأرقام تعليمية فقط وليست إشارة دخول."
            ),
        },
        {
            "text": (
                "🖼️ <b>الجزء 2 — شاهد البنية</b>\n\n"
                f"الاتجاه: {example['side']}\n"
                f"الدخول التعليمي: {example['entry']}\n"
                f"الوقف: {example['stop']}\n"
                f"الهدف: {example['target']}"
            ),
            "visual": "breakout" if "اختراق" in example["title"] or "كسر" in example["title"] else "trend",
            "visual_variant": 0,
            "visual_title": example["title"],
        },
        {
            "text": (
                "🔎 <b>الجزء 3 — لماذا هذا السيناريو منطقي؟</b>\n\n"
                f"{example['why']}\n\n"
                f"1) {example['checks'][0]}\n"
                f"2) {example['checks'][1]}\n"
                f"3) {example['checks'][2]}"
            ),
        },
        {
            "text": (
                "🚫 <b>الجزء 4 — الصورة المعاكسة والفخ</b>\n\n"
                "لا يكفي أن ترى نفس الشكل؛ إذا تغير الموقع أو الإبطال أو نسبة العائد للمخاطرة، "
                "قد تتحول الفكرة الجيدة إلى دخول سيئ."
            ),
            "visual": "process",
            "visual_variant": 1,
            "visual_title": "TRAP VS SETUP",
        },
        {
            "text": (
                "🧪 <b>الجزء 5 — امتحان سريع</b>\n\n"
                "قبل أي دخول اسأل: هل عندي سياق؟ هل أنا عند مستوى؟ هل ظهر تفعيل؟ "
                "أين الإبطال؟ وهل الهدف يعطي مساحة كافية؟"
            ),
        },
        {
            "text": (
                f"✅ <b>انتهى الدرس {lesson_number}</b>\n\n"
                "⏳ <b>انتظر الدرس التالي بعد ساعة لتصبح متداولًا أنجح.</b>\n"
                "الهدف: أن تتعلم كيف يفكر المتداول، لا أن تحفظ صفقة."
            ),
        },
    ]


def build_weekend_lesson(paper, lesson_number):
    """Teach the fixed curriculum from zero to advanced, then run graduate labs."""
    lesson_number = max(1, int(lesson_number))
    slot = lesson_number - 1

    # The full curriculum is strictly sequential: no advanced case study is
    # allowed to jump ahead of foundations the student has not learned yet.
    if lesson_number <= curriculum_size():
        return {
            "lesson_number": lesson_number,
            "kind": "curriculum",
            "parts": academy_parts(slot, lesson_number=lesson_number),
        }

    # After graduation, rotate real V4 cases and scenario drills as practice.
    winners = _successful_trades(paper)
    graduate_number = lesson_number - curriculum_size()
    mode = graduate_number % 3
    if winners and mode == 0:
        trade = winners[(graduate_number // 3 - 1) % len(winners)]
        parts = _historical_parts(trade, lesson_number)
        kind = "historical"
    elif mode == 1:
        parts = _example_parts(graduate_number, lesson_number)
        kind = "scenario"
    else:
        # Revisit the advanced end of the curriculum as spaced repetition.
        advanced_slot = max(0, curriculum_size() - 1 - (graduate_number % min(12, curriculum_size())))
        parts = academy_parts(advanced_slot, lesson_number=lesson_number)
        kind = "advanced_review"
    return {"lesson_number": lesson_number, "kind": kind, "parts": parts}


def maybe_send_weekend_education(store, notifier, paper, now):
    """Run one multi-part lesson: a part every 5m, then a full 1h break."""
    if notifier is None or not weekend_education_window(now):
        return False

    now_ts = float(now.timestamp())

    # Curriculum v2 starts from absolute basics. Reset only academy progress
    # once after deployment; trade history and all trading state remain intact.
    curriculum_version = 3
    if int(store.get("v4_weekend_curriculum_version", 0) or 0) != curriculum_version:
        store.set("v4_weekend_curriculum_version", curriculum_version)
        store.set("v4_weekend_lesson_number", 1)
        store.set("v4_weekend_lesson_state", {})
        store.set("v4_weekend_education_last_sent", None)

    # Style updates may restart only the current lesson presentation while
    # preserving the student's curriculum lesson number and all trading state.
    style_version = 3
    if int(store.get("v4_weekend_lesson_style_version", 0) or 0) != style_version:
        store.set("v4_weekend_lesson_style_version", style_version)
        store.set("v4_weekend_lesson_state", {})

    state = store.get("v4_weekend_lesson_state", {}) or {}
    lesson_number = int(store.get("v4_weekend_lesson_number", 1) or 1)

    if state.get("status") == "cooldown":
        normal_next = float(state.get("next_lesson_at", 0) or 0)
        if tonight_intensive_window(now):
            # A lesson that previously entered the normal 1h cooldown may resume
            # tonight after only 5 minutes from its actual finish.
            accelerated_next = float(state.get("finished_at", now_ts) or now_ts) + 300
            if now_ts < accelerated_next:
                return False
        elif now_ts < normal_next:
            return False
        state = {}

    if not state or state.get("status") not in ("active", "cooldown"):
        lesson = build_weekend_lesson(paper, lesson_number)
        state = {
            "status": "active",
            "lesson": lesson,
            "part_index": 0,
            "next_part_at": now_ts,
            "started_at": now_ts,
        }
        store.set("v4_weekend_lesson_state", state)

    if state.get("status") != "active":
        return False
    if now_ts < float(state.get("next_part_at", 0) or 0):
        return False

    lesson = state.get("lesson") or {}
    parts = lesson.get("parts") or []
    part_index = int(state.get("part_index", 0) or 0)
    if part_index >= len(parts):
        state.update(
            status="cooldown",
            finished_at=now_ts,
            next_lesson_at=now_ts + _between_lesson_cooldown(now),
        )
        store.set("v4_weekend_lesson_state", state)
        return False

    part = parts[part_index]
    if part.get("visual") and hasattr(notifier, "send_photo"):
        image = render_lesson_visual(
            part.get("visual"),
            variant=int(part.get("visual_variant", 0) or 0),
            title=str(part.get("visual_title") or ""),
            side=str(part.get("visual_side") or "شرح"),
        )
        sent = notifier.send_photo(image, caption=part.get("text"))
    else:
        sent = notifier.send(part.get("text", ""))

    if not sent:
        return False

    part_index += 1
    state["part_index"] = part_index
    state["last_sent_at"] = now_ts
    if part_index >= len(parts):
        state["status"] = "cooldown"
        state["finished_at"] = now_ts
        state["next_lesson_at"] = now_ts + _between_lesson_cooldown(now)
        store.set("v4_weekend_lesson_number", lesson_number + 1)
    else:
        state["next_part_at"] = now_ts + 300

    store.set("v4_weekend_lesson_state", state)
    store.set("v4_weekend_education_last_sent", now.isoformat())
    return True
