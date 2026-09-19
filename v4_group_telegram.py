"""Group-capable Telegram transport for Laith V4.

Only the already-paired private owner can bind a group. When a group is bound,
automatic V4 paper notifications go to that group only; private chat remains
available for owner commands and as the fallback destination when no group is bound.
"""
import logging

from v4_telegram import (
    V4Telegram as BaseV4Telegram,
    quick_stats_message,
    stats_message,
    status_message,
    welcome_message,
)

LOG = logging.getLogger("laith.v4.telegram.group")


class V4Telegram(BaseV4Telegram):
    def group_chat(self):
        return str(self.store.get("v4_telegram_group_id") or "")

    def _send_to(self, chat_id, message, label):
        if not self.client or not chat_id:
            return False
        self.client.chat_id = str(chat_id)
        outcome = self.client.send(message)
        LOG.info(
            "telegram_%s_delivery status=%s message_id=%s error=%s",
            label, outcome.status, outcome.message_id, outcome.error,
        )
        return outcome.status == "sent"

    def send(self, message):
        """Send automatic notifications to the bound group, else private fallback."""
        group_id = self.group_chat()
        if group_id:
            return self._send_to(group_id, message, "group")
        return self._send_to(self.paired_chat(), message, "private")

    def send_photo(self, photo_bytes, caption=None):
        """Send an educational image to the bound group, else private fallback."""
        chat_id = self.group_chat() or self.paired_chat()
        if not self.client or not chat_id:
            return False
        self.client.chat_id = str(chat_id)
        outcome = self.client.send_photo(photo_bytes, caption=caption)
        label = "group_photo" if self.group_chat() else "private_photo"
        LOG.info("telegram_%s_delivery status=%s message_id=%s error=%s",
                 label, outcome.status, outcome.message_id, outcome.error)
        return outcome.status == "sent"

    def poll(self):
        if not self.client:
            return
        offset = self.store.get("v4_telegram_update_offset", 0)
        try:
            updates = self.client.read(
                "getUpdates", offset=offset, timeout=0,
                allowed_updates='["message"]', limit=20,
            )
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
            chat_type = chat.get("type")
            private = chat_type == "private" and chat_id and chat_id == sender_id
            group = chat_type in ("group", "supergroup") and bool(chat_id)
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

            elif group and paired and sender_id == paired and command in ("/group", "/share"):
                self.store.set("v4_telegram_group_id", chat_id)
                self.client.chat_id = chat_id
                self.client.send(
                    "✅ <b>تم ربط المجموعة بـ Laith V4</b>\n"
                    "من الآن إشارات V4 السريعة والرسمية وتحديثات الاستمرارية والطوارئ ستصل إلى هذه المجموعة فقط بدل الخاص.\n"
                    "يبقى الخاص متاحًا للأوامر مثل /status و /stats و /quickstats.\n"
                    "📄 الإشارات ورقية/بحثية وليست تنفيذًا على حساب حقيقي."
                )
                LOG.info("telegram_group_paired chat_id_suffix=%s", chat_id[-4:])

            elif group and paired and sender_id == paired and command == "/ungroup":
                if self.group_chat() == chat_id:
                    self.store.set("v4_telegram_group_id", None)
                    self.client.chat_id = chat_id
                    self.client.send(
                        "✅ تم إيقاف إرسال إشارات V4 إلى هذه المجموعة.\n"
                        "ستعود الإشعارات التلقائية إلى الخاص ما دام لا توجد مجموعة مربوطة."
                    )
                    LOG.info("telegram_group_unpaired chat_id_suffix=%s", chat_id[-4:])

            if isinstance(uid, int):
                self.store.set("v4_telegram_update_offset", uid + 1)
