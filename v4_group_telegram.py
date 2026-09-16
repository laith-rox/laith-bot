"""Group-capable Telegram transport for Laith V4.

Only the already-paired private owner can bind a group. Automatic V4 paper
notifications are then mirrored to the owner's private chat and the bound group.
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
        """Mirror automatic notifications to private owner and bound group."""
        private_ok = self._send_to(self.paired_chat(), message, "private")
        group_id = self.group_chat()
        group_ok = True
        if group_id:
            group_ok = self._send_to(group_id, message, "group")
        return private_ok and group_ok

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
                    "من الآن إشارات V4 السريعة والرسمية وتحديثات الاستمرارية ستصل هنا أيضًا.\n"
                    "📄 الإشارات ورقية/بحثية وليست تنفيذًا على حساب حقيقي."
                )
                LOG.info("telegram_group_paired chat_id_suffix=%s", chat_id[-4:])

            elif group and paired and sender_id == paired and command == "/ungroup":
                if self.group_chat() == chat_id:
                    self.store.set("v4_telegram_group_id", None)
                    self.client.chat_id = chat_id
                    self.client.send("✅ تم إيقاف إرسال إشارات V4 إلى هذه المجموعة.")
                    LOG.info("telegram_group_unpaired chat_id_suffix=%s", chat_id[-4:])

            if isinstance(uid, int):
                self.store.set("v4_telegram_update_offset", uid + 1)
