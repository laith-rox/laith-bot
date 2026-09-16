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


def welcome_message():
    return (
        "🥇 <b>Laith V4 — مختبر الذهب</b>\n\n"
        "تم ربط تيليجرام بالنسخة التجريبية المستقلة.\n"
        "📄 الصفقات هنا <b>ورقية/بحثية فقط</b> وليست تنفيذًا على حساب حقيقي.\n\n"
        "الأوامر:\n"
        "/status — آخر تحليل وحالة V4\n"
        "/stats — نتائج الصفقات الورقية"
    )


def status_message(store):
    decision = store.get("v4_last_analysis", {}) or {}
    research = decision.get("v4", {}) or {}
    structure = store.get("v4_last_structure", {}) or {}
    correction = structure.get("correction", {}) or {}
    risk = structure.get("risk", {}) or {}
    active = store.get("v4_active")
    side = decision.get("side", "WAIT")
    reason = decision.get("reason", "—")
    lines = [
        "📊 <b>حالة Laith V4</b>",
        f"القرار: <b>{side}</b>",
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
            "🧪 <b>صفقة ورقية قائمة</b>",
            f"الاتجاه: {active.get('side', '—')}",
            f"الدخول: {_fmt(active.get('entry'))}",
            f"الوقف: {_fmt(active.get('stop'))}",
            f"TP1: {_fmt(active.get('tp1'))}",
            f"TP2: {_fmt(active.get('tp2'))}",
        ])
    else:
        lines.extend(["", "لا توجد صفقة ورقية قائمة حاليًا."])
    return "\n".join(lines)


def stats_message(store):
    stats = store.get("v4_stats", {}) or {}
    measured = stats.get("measured", 0)
    return (
        "📈 <b>إحصاءات V4 الورقية</b>\n"
        f"الصفقات المقاسة: {measured}\n"
        f"صافي R: {stats.get('net_r', 0.0):.3f}\n"
        f"Max Drawdown (R): {stats.get('max_drawdown_r', 0.0):.3f}\n"
        f"إجمالي المحفوظ: {stats.get('all_saved_trades', 0)}\n\n"
        "هذه نتائج تجريبية ولا تثبت أداءً مستقبليًا."
    )


def paper_open_message(trade):
    research = trade.get("research_v4") or {}
    return (
        "🧪 <b>إشارة V4 ورقية جديدة</b>\n\n"
        f"الاتجاه: <b>{trade.get('side')}</b>\n"
        f"الدخول: <b>{_fmt(trade.get('entry'))}</b>\n"
        f"🛑 الوقف: {_fmt(trade.get('stop'))}\n"
        f"🎯 TP1: {_fmt(trade.get('tp1'))}\n"
        f"🎯 TP2: {_fmt(trade.get('tp2'))}\n\n"
        f"الجلسة: {research.get('session', '—')}\n"
        f"التذبذب: {research.get('volatility_regime', '—')}\n"
        f"الماكرو: {research.get('macro_alignment', '—')}\n"
        f"الكسر: {research.get('breakout_state', '—')}\n\n"
        "⚠️ صفقة بحثية ورقية فقط؛ ليست تنفيذًا حقيقيًا ولا ربحًا مضمونًا."
    )


def paper_close_message(trade, stats):
    return (
        "🏁 <b>إغلاق صفقة V4 الورقية</b>\n\n"
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
            updates = self.client.read("getUpdates", offset=offset, timeout=0, allowed_updates='["message"]', limit=20)
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

            if isinstance(uid, int):
                self.store.set("v4_telegram_update_offset", uid + 1)
