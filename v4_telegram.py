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
    """BLACK DIAMOND ROYAL Telegram text fallback; no trading logic changes."""
    side = str(trade.get("side") or "—").upper()
    direction = "🔻 SELL · بيع" if side == "SELL" else "🔺 BUY · شراء" if side == "BUY" else "◈ مراقبة"
    risk_level = str(trade.get("risk_level") or "—")
    reasons = trade.get("risk_reasons") or []
    warning = ("⚠️ " + str(reasons[0])) if reasons else ""
    buy_score = trade.get("buy_score", "—")
    sell_score = trade.get("sell_score", "—")
    if trade.get("entry_action") == "ENTER_NOW":
        action = "🟢 ادخل الآن — بعد مطابقة سعر وسيطك"
    elif trade.get("entry_action") == "WATCH":
        reasons = (trade.get("entry_policy") or {}).get("reasons") or []
        action = "👀 فرصة تحت المراقبة" + (f" — {reasons[0]}" if reasons else "")
    elif trade.get("cautious_entry"):
        action = "🟡 ادخل بحذر — بعد مطابقة سعر وسيطك"
    else:
        action = "👀 مراقبة فقط"
    reference = "⚠️ السعر من إغلاق شمعة 5د، وليس سعرًا حيًا" if trade.get("delayed_reference") else "📡 السعر مرصود؛ طابقه مع وسيطك"
    return (
        "💎 <b>LAITH V4 · BLACK DIAMOND ROYAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{direction}</b>   ◈ M5\n"
        f"✦ القوة: <b>{trade.get('strength', '—')}</b> · <b>{trade.get('score', '—')}/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 STOP  <b>{_fmt(trade.get('stop'))}</b>\n"
        f"🔶 ENTRY  <b>{_fmt(trade.get('entry'))}</b>\n"
        f"🟢 TARGET  <b>{_fmt(trade.get('target'))}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚖️ الشروط: بيع <b>{sell_score}/7</b> · شراء <b>{buy_score}/7</b>\n"
        f"🛡️ المخاطرة: <b>{risk_level}</b>\n"
        f"{warning + chr(10) if warning else ''}"
        f"{reference}\n"
        "📄 إشارة ورقية غير مضمونة\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 الحالة: <b>{action}</b>"
    )

def continuation_message(snapshot):
    side = snapshot.get("side")
    side_label = "شراء 🟢⬆️" if side == "BUY" else "بيع 🔴⬇️" if side == "SELL" else "اتجاه غير متاح"
    def correction_label(value):
        if value is None or str(value).strip().upper() in ("", "NONE", "UNAVAILABLE"):
            return "غير متاح"
        return {"UP": "صاعد", "DOWN": "هابط", "STRONG": "قوي", "MEDIUM": "متوسط", "WEAK": "ضعيف"}.get(str(value).upper(), str(value))
    state = snapshot.get("state", "—")
    marker = "✅" if state == "قوية" else "🟡" if state == "متوسطة" else "🟠" if state == "ضعيفة" else "🔴"
    notes = []
    if snapshot.get("opposite_official"):
        notes.append("اتجاه رسمي معاكس")
    if snapshot.get("adverse_correction"):
        notes.append("تصحيح قوي عكس الصفقة")
    if snapshot.get("failed_break"):
        notes.append("كسر فاشل")
    warning = ("\n⚠️ " + " — ".join(notes[:2])) if notes else ""
    tp1_text = "✅" if snapshot.get("tp1_hit") else "⏳"
    return (
        "💎 <b>LAITH V4 · BLACK DIAMOND ROYAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔄 <b>متابعة | {side_label}</b>\n"
        "⏱ تحديث 5 دقائق · متابعة ورقية\n"
        f"💰 السعر: <b>{_fmt(snapshot.get('price'))}</b> | الدخول: {_fmt(snapshot.get('entry'))}\n"
        f"🛑 الوقف: <b>{_fmt(snapshot.get('stop'))}</b>\n"
        f"🎯 الأهداف: {_fmt(snapshot.get('tp1'))} {tp1_text} | {_fmt(snapshot.get('tp2'))}\n"
        f"{marker} الاستمرارية: <b>{state}</b> · {snapshot.get('score', '—')}/7\n"
        f"↗️ التصحيح: {correction_label(snapshot.get('correction_direction'))} / {correction_label(snapshot.get('correction_strength'))}"
        f"{warning}\n"
        "📄 متابعة فقط — ليست إشارة دخول جديدة"
    )


def paper_open_message(trade):
    research = trade.get("research_v4") or {}
    side = trade.get("side")
    side_label = "شراء 🟢⬆️" if side == "BUY" else "بيع 🔴⬇️" if side == "SELL" else "اتجاه غير متاح"
    return (
        "💎 <b>LAITH V4 · BLACK DIAMOND ROYAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>V4 | {side_label} — صفقة رسمية</b>\n"
        f"⭐ القوة: <b>{trade.get('signal_strength', '—')}</b> · {trade.get('signal_score', '—')}/{trade.get('signal_total', 7)}\n"
        f"💰 الدخول: <b>{_fmt(trade.get('entry'))}</b>\n"
        f"🛑 الوقف: <b>{_fmt(trade.get('stop'))}</b>\n"
        f"🎯 الأهداف: <b>{_fmt(trade.get('tp1'))}</b> | <b>{_fmt(trade.get('tp2'))}</b>\n"
        f"🕒 الجلسة: {research.get('session', '—')}\n"
        f"⚠️ كسر: {research.get('breakout_state', '—')} · ماكرو: {research.get('macro_alignment', '—')}\n"
        "📄 صفقة ورقية بحثية — ليست تنفيذًا حقيقيًا"
    )


def paper_close_message(trade, stats):
    outcome = trade.get("outcome", "—")
    outcome_marker = "🟢" if outcome == "TP2" else "🔴" if outcome in ("STOP", "PROTECTED_STOP") else "🟡"
    return (
        "💎 <b>LAITH V4 · BLACK DIAMOND ROYAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏁 <b>إغلاق صفقة V4</b>\n"
        f"{outcome_marker}① النتيجة: <b>{outcome}</b>\n"
        f"🔵② الاتجاه: {trade.get('side', '—')}\n"
        f"🔵③ R للصفقة: {trade.get('r', '—')}\n"
        f"🔵④ صافي R: {stats.get('net_r', 0.0):.3f}\n"
        "📄 نتيجة ورقية/تجريبية"
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

    def send_photo(self, photo_bytes, caption=None):
        if not self.client:
            return False
        chat_id = self.paired_chat()
        if not chat_id:
            return False
        self.client.chat_id = chat_id
        outcome = self.client.send_photo(photo_bytes, caption=caption)
        LOG.info("telegram_photo_delivery status=%s message_id=%s error=%s",
                 outcome.status, outcome.message_id, outcome.error)
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
