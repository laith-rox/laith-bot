"""Group-capable Telegram transport for Laith V4.

Only the already-paired private owner can bind a group. When a group is bound,
automatic V4 paper notifications go to that group only; private chat remains
available for owner commands and as the fallback destination when no group is bound.
"""
import logging
import html
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

from v4_free_chat import respond as free_chat_respond
from gigi_image import configured as gigi_image_configured, generate_and_deliver as gigi_image_generate_and_deliver
from gigi_persona import (
    configured as gigi_configured,
    generate as gigi_generate,
    history_items as gigi_history_items,
)

from v4_telegram import (
    V4Telegram as BaseV4Telegram,
    quick_stats_message,
    stats_message,
    status_message,
    welcome_message,
)

LOG = logging.getLogger("laith.v4.telegram.group")


class V4Telegram(BaseV4Telegram):
    def _gigi_quota(self, kind, chat_id):
        """Small owner-only per-day safety budget; never touches trading counters."""
        defaults = {"text": 60, "image": 12}
        if kind not in defaults:
            return False
        env_name = "GIGI_DAILY_TEXT_LIMIT" if kind == "text" else "GIGI_DAILY_IMAGE_LIMIT"
        try:
            limit = max(1, min(1000, int(os.getenv(env_name, defaults[kind]))))
        except (ValueError, TypeError):
            limit = defaults[kind]
        today = datetime.now(ZoneInfo("Asia/Hebron")).date().isoformat()
        usage = self.store.get("v4_gigi_daily_usage")
        if not isinstance(usage, dict) or usage.get("date") != today:
            usage = {"date": today, "text": 0, "image": 0}
        try:
            count = max(0, int(usage.get(kind, 0)))
        except (ValueError, TypeError):
            count = 0
        if count >= limit:
            self._send_to(
                chat_id,
                "⏳ وصلنا للحد اليومي لطلبات جيجي. بيبدأ عدّ جديد "
                "بعد منتصف الليل بتوقيت فلسطين. بنقدر نضبط الحد من Railway.",
                "gigi_daily_limit",
            )
            return False
        usage[kind] = count + 1
        self.store.set("v4_gigi_daily_usage", usage)
        return True

    def _gigi_finish(self):
        """Deliver finished chat without blocking trading or polling on API I/O."""
        job = getattr(self, "_gigi_job", None)
        if not job or not job["future"].done():
            return
        self._gigi_job = None
        try:
            answer = job["future"].result()
        except Exception as exc:
            # Log only a fixed error identifier; never log key, request, or provider body.
            codes = {
                "gigi_auth_invalid": "🔐 مفتاح OpenAI غير مقبول. افحص المفتاح في Railway.",
                "gigi_permission_denied": "🔒 مفتاح جيجي ما عنده صلاحية طلب ردود OpenAI. راجع Permissions في المنصّة.",
                "gigi_quota_exceeded": "💳 رصيد أو حد صرف OpenAI API ما بسمح بالرد. افحص Billing في منصة OpenAI.",
                "gigi_rate_limited": "⏱️ وصلنا لحد الطلبات المؤقت لـ OpenAI. جرّب بعد شوي.",
                "gigi_model_unavailable": "🤖 النموذج المختار لجيجي مش متاح لهذا المفتاح. بدنا نراجع GIGI_MODEL.",
                "gigi_bad_request": "⚙️ طلب جيجي إلى OpenAI غير مقبول. بدنا نراجع إعدادات النموذج.",
                "gigi_provider_unavailable": "💌 خدمة OpenAI غير متاحة مؤقتًا. جرّب بعد شوي.",
                "gigi_network_timeout": "⏱️ اتصال جيجي بـ OpenAI انتهت مهلته. جرّب بعد شوي.",
                "gigi_network_unavailable": "🌐 تعذر الاتصال بخدمة OpenAI من Railway. جرّب بعد شوي.",
            }
            reason = str(exc)
            category = reason if reason in codes else "gigi_unknown_error"
            LOG.warning("gigi_chat_request_failed category=%s", category)
            self.store.set("v4_gigi_last_api_error", category)
            self._send_to(
                job["chat"],
                codes.get(category, "💌 صار خطأ غير متوقع عند اتصال جيجي؛ راجع سجلات البوت."),
                "gigi_error",
            )
            return
        # Telegram transport uses HTML. Escape all model text (never raw HTML).
        if self._send_to(job["chat"], html.escape(answer, quote=False), "gigi"):
            self.store.set("v4_gigi_last_api_error", "")
            history = gigi_history_items(
                [*job["history"], {"role": "user", "content": job["message"]},
                 {"role": "assistant", "content": answer}]
            )
            self.store.set("v4_gigi_private_history", history)

    def _gigi_image_finish(self):
        job = getattr(self, "_gigi_image_job", None)
        if not job or not job["future"].done():
            return
        self._gigi_image_job = None
        try:
            delivered = job["future"].result()
        except Exception:
            LOG.warning("gigi_image_request_failed")
            self._send_to(job["chat"], "🌹 صورة جيجي ما زبطت هالمرة، جرّب بعدين.", "gigi_image_error")
            return
        # The photo was uploaded in the background worker; never block polling.
        LOG.info("gigi_image_delivery confirmed=%s", bool(delivered))

    def _gigi_image_schedule(self, request_text, chat_id):
        if not gigi_image_configured():
            self._send_to(
                chat_id,
                "🌹 استوديو الصور اختياري ولسه مش مفعل؛ بدّه GIGI_IMAGES_ENABLED=1 "
                "ومفتاح API للصور، وهي طلبات مدفوعة منفصلة.",
                "gigi_image_setup",
            )
            return
        if getattr(self, "_gigi_job", None) or getattr(self, "_gigi_image_job", None):
            self._send_to(chat_id, "💌 في طلب جيجي سابق قيد التحضير، استنى اكتماله.", "gigi_busy")
            return
        now = time.time()
        last = float(self.store.get("v4_gigi_last_image_time", 0) or 0)
        if now - last < 600:
            self._send_to(chat_id, "⏱️ استوديو الصور يسمح بصورة واحدة كل عشر دقايق.", "gigi_image_cooldown")
            return
        if not self._gigi_quota("image", chat_id):
            return
        if not hasattr(self, "_gigi_executor"):
            self._gigi_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gigi-chat")
        self.store.set("v4_gigi_last_image_time", now)
        job = self._gigi_executor.submit(gigi_image_generate_and_deliver, request_text, str(chat_id))
        self._gigi_image_job = {"future": job, "chat": str(chat_id)}
        self._send_to(chat_id, "🎨 جيجي بتحضّر صورة جديدة من حكايتنا.", "gigi_image_start")

    def _gigi_schedule(self, text, chat_id):
        """One in-flight request, private paired owner only; no market state reads."""
        if not gigi_configured():
            self._send_to(
                chat_id,
                "🔐 جيجي جاهزة كميزة اختيارية، بس لازم GIGI_OPENAI_API_KEY "
                "يتضاف بأمان في إعدادات Railway. أوامر الذهب بتضل شغالة.",
                "gigi_setup",
            )
            return
        if getattr(self, "_gigi_job", None) or getattr(self, "_gigi_image_job", None):
            self._send_to(chat_id, "💌 جيجي لسه بتحضّر الرد السابق، ابعت رسالتك بعده.", "gigi_busy")
            return
        if not hasattr(self, "_gigi_executor"):
            self._gigi_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gigi-chat")
        message = str(text).strip()[:1200]
        if not message:
            return
        if not self._gigi_quota("text", chat_id):
            return
        history = gigi_history_items(self.store.get("v4_gigi_private_history"))
        future = self._gigi_executor.submit(gigi_generate, message, history)
        self._gigi_job = {
            "future": future, "chat": str(chat_id), "message": message,
            "history": history,
        }
        LOG.info("gigi_chat_queued")

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
        self._gigi_finish()
        self._gigi_image_finish()
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
            # A malformed update must not crash the worker or advance its cursor.
            if not isinstance(update, dict):
                LOG.warning("telegram_update_invalid type=non_object")
                continue
            uid = update.get("update_id")
            # Skip replays before commands, not just when advancing the cursor.
            if type(uid) is not int:
                continue
            try:
                current_offset = max(0, int(self.store.get("v4_telegram_update_offset", 0)))
            except (TypeError, ValueError):
                current_offset = 0
            if uid < current_offset:
                continue
            message = update.get("message")
            if not isinstance(message, dict):
                LOG.warning("telegram_update_invalid type=message_not_object")
                # Do not replay a permanently malformed update forever.
                self.store.set("v4_telegram_update_offset", max(current_offset, uid + 1))
                continue
            chat = message.get("chat")
            sender = message.get("from")
            text = message.get("text")
            if not isinstance(chat, dict) or not isinstance(sender, dict) or not isinstance(text, str):
                LOG.warning("telegram_update_invalid type=message_fields")
                self.store.set("v4_telegram_update_offset", max(current_offset, uid + 1))
                continue
            text = text.strip()
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
                    self.client.send(free_chat_respond("/menu", self.store))
                    LOG.info("telegram_paired chat_id_suffix=%s", chat_id[-4:])
                elif self.pair_code:
                    self.client.chat_id = chat_id
                    self.client.send("🔐 كود الربط غير صحيح.")

            elif private and paired and chat_id == paired:
                # Gigi mode is isolated from signals and accessible to owner only.
                self.client.chat_id = paired
                if command in ("/gigi", "/جيجي"):
                    if not gigi_configured():
                        self._gigi_schedule("", paired)
                    else:
                        self.store.set("v4_gigi_private_mode", True)
                        tail = text[len(words[0]):].strip()
                        if tail:
                            self._gigi_schedule(tail, paired)
                        else:
                            self.client.send(
                                "👑 أهلين بأميري! جيجي هون في حكايتنا الخاصة ❤️\n"
                                "احكي معي طبيعي؛ /laith للرجوع لبوت الإشارات، "
                                "/gigireset لمسح ذاكرة جيجي."
                            )
                elif command in ("/laith", "/exitgigi"):
                    self.store.set("v4_gigi_private_mode", False)
                    # In-flight result is ignored after leaving private mode.
                    self._gigi_job = None
                    self.client.send("🥇 رجعنا لوضع بوت ليث. إشارات التداول مستقلة عن جيجي.")
                elif command in ("/gigiphoto", "/gigiimage"):
                    request = text[len(words[0]):].strip()
                    self._gigi_image_schedule(request, paired)
                elif command == "/gigireset":
                    self.store.set("v4_gigi_private_history", [])
                    self._gigi_job = None
                    self.client.send("🧹 مسحت سجل محادثة جيجي المحفوظ في هالبوت.")
                elif self.store.get("v4_gigi_private_mode", False) and not command.startswith("/"):
                    self._gigi_schedule(text, paired)
                else:
                    # Preserve existing gold/BTC commands and deterministic fallbacks.
                    reply = free_chat_respond(text, self.store)
                    if reply:
                        self.client.send(reply)

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

            # Never rewind the cursor on overlapping/out-of-order updates.
            if type(uid) is int:
                current = self.store.get("v4_telegram_update_offset", 0)
                try:
                    current = max(0, int(current))
                except (TypeError, ValueError):
                    current = 0
                if uid + 1 > current:
                    self.store.set("v4_telegram_update_offset", uid + 1)
