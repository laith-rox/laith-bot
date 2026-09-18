"""Telegram pairing and paper-trade notifications for Laith V4.

This transport is isolated from the official bot. It only reports V4 paper/research
state and never sends broker orders.
"""
import logging

from transport import Telegram

LOG = logging.getLogger("laith.v4.telegram")


def _fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _quick_history_line(trade):
    try:
        sample = int(trade.get("historical_sample", 0) or 0)
    except (TypeError, ValueError):
        sample = 0
    rate = trade.get("historical_positive_rate")
    positive = trade.get("historical_positive")
    if sample > 0 and rate is not None:
        return (
            f"📚 النتائج المرصودة: <b>{positive}/{sample} موجبة ({rate}%)</b> "
            "— وصف تاريخي للعينة، وليس احتمال نجاح للصفقة الحالية."
        )
    return "📚 النتائج المرصودة: لا توجد عينة مقاسة كافية بعد."


def _strength_adjustment_line(trade):
    raw = trade.get("raw_strength")
    shown = trade.get("strength")
    adjustments = trade.get("strength_adjustments") or []
    if raw and shown and raw != shown:
        reason = " — ".join(str(x) for x in adjustments) if adjustments else "معايرة المخاطرة"
        return f"🧭 القوة الخام: {raw} → المعروضة: <b>{shown}</b> ({reason})"
    return None


def welcome_message():
    return (
        "🥇 <b>Laith V4 — مختبر الذهب</b>\n\n"
        "تم ربط تيليجرام بالنسخة التجريبية المستقلة.\n"
        "⚡ يفحص صفقة سريعة كل 5 دقائق، وتبقى السريعة مستقلة حتى لو كانت صفقة V4 الرسمية قائمة.\n"
        "🔴 إذا كانت الظروف خطرة لا تختفي الصفقة السريعة؛ يظهر عليها مستوى المخاطرة وأسباب التحذير.\n"
        "🧭 كلمة قوية تُعاير الآن: لا تبقى قوية إذا كانت المخاطرة مرتفعة أو القرار الرسمي WAIT.\n"
        "📚 تظهر النتائج المرصودة من الصفقات السريعة السابقة كبيانات تاريخية، وليست احتمال نجاح.\n"
        "🔄 الصفقة الرسمية القائمة تحصل على تحديث استمرارية كل 5 دقائق.\n"
        "📄 كل الصفقات هنا <b>ورقية/بحثية فقط</b> وليست تنفيذًا على حساب حقيقي.\n\n"
        "الأوامر:\n"
        "/status — آخر تحليل وحالة V4\n"
        "/stats — نتائج الصفقات الرسمية الورقية\n"
        "/quickstats — نتائج الصفقات السريعة الورقية"
    )


def status_message(store):
    decision = store.get("v4_last_analysis", {}) or {}
    research = decision.get("v4", {}) or {}
    structure = store.get("v4_last_structure", {}) or {}
    correction = structure.get("correction", {}) or {}
    risk = structure.get("risk", {}) or {}
    active = store.get("v4_active")
    quick = store.get("v4_quick_last") or {}
    continuation = store.get("v4_last_continuation") or {}
    side = decision.get("side", "WAIT")
    reason = decision.get("reason", "—")
    lines = [
        "📊 <b>حالة Laith V4</b>",
        f"القرار الرسمي: <b>{side}</b>",
        f"السبب: {reason}",
        f"الجلسة: {research.get('session', '—')}",
        f"التذبذب: {research.get('volatility_regime', '—')} ({research.get('volatility_percentile', '—')}%)",
        f"الماكرو: {research.get('macro_alignment', '—')}",
        f"الدعم: {_fmt((structure.get('support') or {}).get('center'))}",
        f"المقاومة: {_fmt((structure.get('resistance') or {}).get('center'))}",
        f"التصحيح: {correction.get('direction', '—')} / {correction.get('strength', '—')}",
        f"وقف هيكلي مرجعي: {_fmt(risk.get('stop'))}",
    ]
    if active:
        lines.extend([
            "",
            "✅ <b>صفقة V4 الرسمية الورقية قائمة</b>",
            f"الاتجاه: {active.get('side', '—')}",
            f"الدخول: {_fmt(active.get('entry'))}",
            f"الوقف: {_fmt(active.get('stop'))}",
            f"TP1: {_fmt(active.get('tp1'))}",
            f"TP2: {_fmt(active.get('tp2'))}",
        ])
        if continuation:
            lines.extend([
                f"استمرارية آخر فحص: <b>{continuation.get('state', '—')}</b>",
                f"الشروط: {continuation.get('score', '—')}/7 = {continuation.get('condition_percent', '—')}%",
            ])
    else:
        lines.extend(["", "لا توجد صفقة رسمية ورقية قائمة حاليًا."])
    if quick:
        lines.extend([
            "",
            "⚡ <b>آخر صفقة سريعة</b>",
            f"الاتجاه: {quick.get('side', '—')} | القوة المعروضة: {quick.get('strength', '—')}",
            f"المخاطرة: {quick.get('risk_level', '—')}",
            f"الشروط: {quick.get('score', '—')}/7 = {quick.get('condition_percent', '—')}%",
        ])
        adjusted = _strength_adjustment_line(quick)
        if adjusted:
            lines.append(adjusted)
        lines.extend([
            _quick_history_line(quick),
            f"RSI: {_fmt(quick.get('rsi'))}",
            f"الدخول: {_fmt(quick.get('entry'))} | الهدف: {_fmt(quick.get('target'))}",
        ])
    return "\n".join(lines)


def stats_message(store):
    stats = store.get("v4_stats", {}) or {}
    measured = stats.get("measured", 0)
    return (
        "📈 <b>إحصاءات V4 الرسمية الورقية</b>\n"
        f"الصفقات المقاسة: {measured}\n"
        f"صافي R: {stats.get('net_r', 0.0):.3f}\n"
        f"Max Drawdown (R): {stats.get('max_drawdown_r', 0.0):.3f}\n"
        f"إجمالي المحفوظ: {stats.get('all_saved_trades', 0)}\n\n"
        "هذه نتائج تجريبية ولا تثبت أداءً مستقبليًا."
    )


def quick_stats_message(store):
    stats = store.get("v4_quick_stats", {}) or {}
    return (
        "⚡ <b>إحصاءات الصفقات السريعة — V4</b>\n"
        f"الإشارات المحفوظة: {stats.get('saved', 0)}\n"
        f"الصفقات المقاسة: {stats.get('measured', 0)}\n"
        f"صافي R: {stats.get('net_r', 0.0):.3f}\n"
        f"Max Drawdown (R): {stats.get('max_drawdown_r', 0.0):.3f}\n\n"
        "القوة ونسبة الشروط تصف اكتمال القواعد، وليست احتمال نجاح."
    )


def quick_message(trade):
    conditions = []
    for item in trade.get("conditions") or []:
        conditions.append(("✅" if item.get("ok") else "❌") + " " + str(item.get("name", "شرط")))
    checklist = "\n".join(conditions)
    risk_level = trade.get("risk_level", "—")
    risk_marker = "🔴" if risk_level == "مرتفعة" else "🟡" if risk_level == "متوسطة" else "🟢"
    reasons = trade.get("risk_reasons") or []
    risk_text = " — ".join(str(x) for x in reasons) if reasons else "لا توجد تحذيرات إضافية"
    adjustment = _strength_adjustment_line(trade)
    adjustment_text = (adjustment + "\n") if adjustment else ""
    return (
        "⚡ <b>صفقة سريعة — V4 (ورقية)</b>\n\n"
        f"الاتجاه: <b>{trade.get('side', '—')}</b>\n"
        f"📊 تحقق الشروط: <b>{trade.get('score', '—')}/7 = {trade.get('condition_percent', '—')}%</b>\n"
        f"🧭 القوة المعروضة: <b>{trade.get('strength', '—')}</b>\n"
        f"{adjustment_text}"
        f"{_quick_history_line(trade)}\n"
        f"{risk_marker} المخاطرة: <b>{risk_level}</b>\n"
        f"⚠️ ملاحظات: {risk_text}\n"
        f"📈 RSI: <b>{_fmt(trade.get('rsi'))}</b>\n\n"
        f"{checklist}\n\n"
        f"💰 الدخول: <b>{_fmt(trade.get('entry'))}</b>\n"
        f"🛑 وقف الخسارة: {_fmt(trade.get('stop'))}\n"
        f"🎯 الهدف السريع: {_fmt(trade.get('target'))}\n"
        f"⚖️ R:R: 1:{float(trade.get('rr', 0)):.2f}\n"
        "⏱️ الصلاحية: 20 دقيقة\n\n"
        f"الجلسة: {trade.get('session', '—')} | التذبذب: {trade.get('volatility_regime', '—')}\n"
        "↔️ المسار السريع مستقل عن الصفقة الرسمية وقد يعمل معها بنفس الوقت.\n"
        "⚠️ نسبة الشروط والقوة ليستا احتمال ربح. الصفقة بحثية ورقية فقط."
    )


def continuation_message(snapshot):
    state = snapshot.get("state", "—")
    marker = "✅" if state == "قوية" else "🟡" if state == "متوسطة" else "🟠" if state == "ضعيفة" else "🔴"
    notes = []
    if snapshot.get("opposite_official"):
        notes.append("ظهر اتجاه رسمي معاكس في الفحص الحالي")
    if snapshot.get("adverse_correction"):
        notes.append("رُصد تصحيح قوي عكس اتجاه الصفقة")
    if snapshot.get("failed_break"):
        notes.append("ظهر كسر فاشل")
    note_text = ("\n⚠️ " + " — ".join(notes)) if notes else ""
    tp1_text = "✅ تم رصده" if snapshot.get("tp1_hit") else "لم يُرصد بعد"
    return (
        "🔄 <b>تحديث 5 دقائق — استمرارية صفقة V4 الرسمية</b>\n\n"
        f"الاتجاه: <b>{snapshot.get('side', '—')}</b>\n"
        f"{marker} الاستمرارية الحالية: <b>{state}</b>\n"
        f"📊 شروط الاتجاه: <b>{snapshot.get('score', '—')}/7 = {snapshot.get('condition_percent', '—')}%</b>\n"
        f"📈 RSI: {_fmt(snapshot.get('rsi'))}\n"
        f"💰 السعر المرجعي الحالي: {_fmt(snapshot.get('price'))}\n\n"
        f"الدخول: {_fmt(snapshot.get('entry'))}\n"
        f"🛑 الوقف الحالي: {_fmt(snapshot.get('stop'))}\n"
        f"🎯 TP1: {_fmt(snapshot.get('tp1'))} — {tp1_text}\n"
        f"🎯 TP2: {_fmt(snapshot.get('tp2'))}\n"
        f"الكسر: {snapshot.get('breakout_state', '—')} | التصحيح: {snapshot.get('correction_direction', '—')} / {snapshot.get('correction_strength', '—')}"
        f"{note_text}\n\n"
        "⚠️ هذا تحديث شروط واستمرارية للصفقة الورقية، وليس ضمانًا باستمرار الحركة."
    )


def paper_open_message(trade):
    research = trade.get("research_v4") or {}
    return (
        "✅ <b>صفقة V4 الرسمية — ورقية</b>\n\n"
        f"الاتجاه: <b>{trade.get('side')}</b>\n"
        f"📊 تحقق الشروط: <b>{trade.get('signal_score', '—')}/{trade.get('signal_total', 7)}</b>\n"
        f"🧭 قوة الإشارة: <b>{trade.get('signal_strength', '—')}</b>\n"
        f"الدخول: <b>{_fmt(trade.get('entry'))}</b>\n"
        f"🛑 الوقف: {_fmt(trade.get('stop'))}\n"
        f"🎯 TP1: {_fmt(trade.get('tp1'))}\n"
        f"🎯 TP2: {_fmt(trade.get('tp2'))}\n\n"
        f"الجلسة: {research.get('session', '—')}\n"
        f"التذبذب: {research.get('volatility_regime', '—')}\n"
        f"الماكرو: {research.get('macro_alignment', '—')}\n"
        f"الكسر: {research.get('breakout_state', '—')}\n\n"
        "⚠️ رسمية داخل نظام V4 لكنها ما زالت صفقة بحثية ورقية؛ ليست تنفيذًا حقيقيًا ولا ربحًا مضمونًا."
    )


def paper_close_message(trade, stats):
    return (
        "🏁 <b>إغلاق صفقة V4 الرسمية الورقية</b>\n\n"
        f"الاتجاه: {trade.get('side', '—')}\n"
        f"النتيجة: <b>{trade.get('outcome', '—')}</b>\n"
        f"R للصفقة: {trade.get('r', '—')}\n"
        f"صافي R للتجربة: {stats.get('net_r', 0.0):.3f}\n"
        f"Max Drawdown: {stats.get('max_drawdown_r', 0.0):.3f}R\n\n"
        "📄 النتيجة ورقية/تجريبية."
    )


class V4Telegram:
    def __init__(self, token, store, chat_id=None, pair_code=None, client_cls=Telegram):
        self.store = store
        self.pair_code = str(pair_code or "").strip()
        self.client = None
        if token:
            saved = str(chat_id or store.get("v4_telegram_chat_id") or "0")
            self.client = client_cls(token, saved)
            if chat_id:
                self.store.set("v4_telegram_chat_id", str(chat_id))

    def paired_chat(self):
        return str(self.store.get("v4_telegram_chat_id") or "")

    def send(self, message):
        if not self.client:
            return False
        chat_id = self.paired_chat()
        if not chat_id:
            return False
        self.client.chat_id = chat_id
        outcome = self.client.send(message)
        LOG.info("telegram_delivery status=%s message_id=%s error=%s", outcome.status, outcome.message_id, outcome.error)
        return outcome.status == "sent"

    def poll(self):
        if not self.client:
            return
        offset = self.store.get("v4_telegram_update_offset", 0)
        try:
            updates = self.client.read("getUpdates", offset=offset, timeout=0, allowed_updates='[\"message\"]', limit=20)
        except RuntimeError as exc:
            LOG.warning("telegram_poll_error reason=%s", exc)
            return
        if not isinstance(updates, list):
            return
        for update in updates:
            uid = update.get("update_id")
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            sender = message.get("from") or {}
            text = (message.get("text") or "").strip()
            chat_id = str(chat.get("id") or "")
            sender_id = str(sender.get("id") or "")
            private = chat.get("type") == "private" and chat_id and chat_id == sender_id
            paired = self.paired_chat()
            words = text.split()
            command = words[0].split("@")[0].lower() if words else ""

            if private and not paired and command == "/start":
                supplied = words[1] if len(words) > 1 else ""
                if self.pair_code and supplied == self.pair_code:
                    self.store.set("v4_telegram_chat_id", chat_id)
                    self.client.chat_id = chat_id
                    self.client.send(welcome_message())
                    LOG.info("telegram_paired chat_id_suffix=%s", chat_id[-4:])
                elif self.pair_code:
                    self.client.chat_id = chat_id
                    self.client.send("🔐 كود الربط غير صحيح.")
            elif private and paired and chat_id == paired:
                self.client.chat_id = paired
                if command in ("/start", "/help"):
                    self.client.send(welcome_message())
                elif command == "/status":
                    self.client.send(status_message(self.store))
                elif command == "/stats":
                    self.client.send(stats_message(self.store))
                elif command == "/quickstats":
                    self.client.send(quick_stats_message(self.store))

            if isinstance(uid, int):
                self.store.set("v4_telegram_update_offset", uid + 1)
