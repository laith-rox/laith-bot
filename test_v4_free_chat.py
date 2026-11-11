"""Regression tests: offline owner-only Arabic Telegram assistant; no LLM API."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import Store
from v4_free_chat import respond
from v4_group_telegram import V4Telegram


class Outcome:
    status = "sent"
    message_id = 1
    error = None


class FakeClient:
    def __init__(self, token, chat_id):
        self.chat_id = str(chat_id)
        self.sent = []
        self.updates = []

    def read(self, method, **kwargs):
        result = list(self.updates)
        self.updates.clear()
        return result

    def send(self, message):
        self.sent.append((str(self.chat_id), message))
        return Outcome()


def update(uid, sender, chat, body, kind="private"):
    return {
        "update_id": uid,
        "message": {
            "chat": {"id": chat, "type": kind},
            "from": {"id": sender},
            "text": body,
        },
    }


class FreeChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "data.sqlite")
        self.store.set("v4_telegram_chat_id", "111")
        self.tg = V4Telegram("fake", self.store, client_cls=FakeClient)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_help_is_honest_about_api_and_trading(self):
        text = respond("جيجي، شو بتعملي؟", self.store)
        self.assertIn("/btcstatus", text)
        self.assertIn("محادثة منفصلة عبر API اختياري", text)
        self.assertIn("/gigi", text)
        self.assertIn("ولا تفتح", text)

    def test_gold_status_answers_from_saved_data(self):
        self.store.set("v4_last_analysis", {"side": "WAIT", "reason": "no_quote"})
        answer = respond("جيجي شو وضع الذهب؟", self.store)
        self.assertIn("WAIT", answer)
        self.assertIn("no_quote", answer)
        self.assertIn("محفوظة", answer)

    def test_btc_off_is_explicit_not_pretend_live(self):
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "0"}):
            self.assertIn("متوقفة", respond("/btcstatus", self.store))
            self.assertIn("معطّل", respond("ليش البيتكوين ما دخل؟", self.store))
            self.assertNotIn("SIGNAL", respond("/btcstatus", self.store))

    def test_btc_wait_reason_from_stored_data(self):
        self.store.set("v4_btc_status", {"status": "WAIT", "reason": "h1_h4_not_aligned", "score": 4})
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            answer = respond("جيجي ليش البيتكوين ما دخل؟", self.store)
            self.assertIn("مش متوافق", answer)
            self.assertIn("4/7", respond("/btcstatus", self.store))

    def test_screenshot_followup_direction_uses_last_btc_context(self):
        from datetime import datetime, timezone
        self.store.set("v4_btc_status", {
            "status": "WAIT", "reason": "h1_h4_not_aligned", "score": None,
            "h1_trend": "BUY", "h4_trend": "SELL",
            "time": datetime.now(timezone.utc).isoformat(),
        })
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            first = respond("جيجي شو وضع البيتكوين؟", self.store)
            self.assertIn("بيتكوين", first)
            self.assertEqual(self.store.get("v4_chat_last_market"), "BTC")
            answer = respond("ع اغلب وين اتجه؟", self.store)
            self.assertIn("محايد", answer)
            self.assertIn("H1", answer)
            self.assertIn("H4", answer)
            self.assertNotIn("ChatGPT بدون ربط", answer)

    def test_screenshot_forecast_is_not_repeated_direction_card(self):
        from datetime import datetime, timezone
        self.store.set("v4_btc_status", {
            "status": "WAIT", "reason": "h1_h4_not_aligned",
            "h1_trend": "WAIT", "h4_trend": "SELL",
            "time": datetime.now(timezone.utc).isoformat()
        })
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            respond("جيجي شو اتجاه البيتكوين؟", self.store)
            direction = respond("وين متجه؟", self.store)
            forecast = respond("توقعك شو", self.store)
        self.assertIn("الضغط الهابط", forecast)
        self.assertIn("H4", forecast)
        self.assertIn("H1", forecast)
        self.assertIn("انتظار", forecast)
        self.assertNotEqual(forecast, direction)
        self.assertNotIn("ChatGPT بدون ربط", forecast)

    def test_forecast_without_topic_or_timestamp_does_not_guess(self):
        self.assertIn("الذهب ولا البيتكوين", respond("توقعك شو", self.store))
        self.store.set("v4_chat_last_market", "BTC")
        self.store.set("v4_btc_status", {"h4_trend": "SELL", "h1_trend": "WAIT"})
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            text = respond("شو رأيك بالسوق", self.store)
        self.assertIn("ما عندي فحص", text)

    def test_btc_forecast_fresh_align_and_stale_fail_closed(self):
        from datetime import datetime, timedelta, timezone
        self.store.set("v4_chat_last_market", "BTC")
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            self.store.set("v4_btc_status", {
                "status": "WAIT", "h1_trend": "BUY", "h4_trend": "BUY",
                "time": datetime.now(timezone.utc).isoformat()
            })
            aligned = respond("توقعك شو؟", self.store)
            self.assertIn("صاعد", aligned)
            self.assertIn("تأكيد", aligned)
            self.store.set("v4_btc_status", {
                "status": "WAIT", "h1_trend": "BUY", "h4_trend": "BUY",
                "time": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            })
            self.assertIn("صار قديم", respond("توقعك شو", self.store))

    def test_screenshot_next_entry_question_avoids_promising_time(self):
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            respond("جيجي شو وضع البيتكوين؟", self.store)
            reply = respond("متا هيكون في اشاره لدخول", self.store)
            self.assertIn("كل 15 دقيقة", reply)
            self.assertIn("ما بقدر أحدد", reply)
            self.assertNotIn("ChatGPT بدون ربط", reply)

    def test_direction_and_signal_time_when_market_unspecified(self):
        answer = respond("على الأغلب وين اتجاهه؟", self.store)
        self.assertIn("الذهب ولا البيتكوين", answer)
        self.assertIsNone(self.store.get("v4_chat_last_market"))
        later = respond("متى هيكون في اشارة دخول؟", self.store)
        self.assertIn("الذهب ولا البيتكوين", later)

    def test_btc_bias_is_not_deduction_from_unstamped_wait(self):
        self.store.set("v4_chat_last_market", "BTC")
        self.store.set("v4_btc_status", {
            "status": "WAIT", "reason": "h1_h4_not_aligned",
        })
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            answer = respond("وين اتجاهه؟", self.store)
            self.assertIn("بدون توقيت موثّق", answer)

    def test_owner_telegram_followups_and_offline_no_order_writes(self):
        from datetime import datetime, timezone
        self.store.set("v4_btc_status", {
            "status": "WAIT", "reason": "h1_h4_not_aligned",
            "h1_trend": "BUY", "h4_trend": "SELL",
            "time": datetime.now(timezone.utc).isoformat()
        })
        self.tg.client.updates = [
            update(50, 111, 111, "جيجي شو وضع البيتكوين؟"),
            update(51, 111, 111, "ع اغلب وين اتجه؟"),
            update(52, 111, 111, "متا هيكون في اشاره لدخول"),
        ]
        with patch.dict(os.environ, {"V4_BTC_SIGNALS_ENABLED": "1"}):
            self.tg.poll()
        self.assertEqual(len(self.tg.client.sent), 3)
        self.assertIn("محايد", self.tg.client.sent[1][1])
        self.assertIn("كل 15 دقيقة", self.tg.client.sent[2][1])
        self.assertIsNone(self.store.get("v4_active"))
        self.assertEqual(self.store.get("v4_telegram_update_offset"), 53)

    def test_no_broker_write_from_stop_or_open_requests(self):
        before = dict(self.store.db.execute("SELECT key,value FROM kv").fetchall())
        reply = respond("جيجي شغل البوت وافتح صفقة", self.store)
        after = dict(self.store.db.execute("SELECT key,value FROM kv").fetchall())
        self.assertEqual(before, after)
        self.assertIn("ما بفتح صفقات", reply)

    def test_unknown_message_does_not_hallucinate_market_price(self):
        text = respond("كم سعر السوق اللحظي هلأ بالدولار؟", self.store)
        self.assertIn("ما بقدر", text)
        self.assertNotIn("100000", text)

    def test_owner_private_receives_response(self):
        self.tg.client.updates = [update(20, 111, 111, "جيجي شو وضع الذهب")]
        self.tg.poll()
        self.assertEqual(len(self.tg.client.sent), 1)
        self.assertEqual(self.tg.client.sent[0][0], "111")
        self.assertIn("للذهب", self.tg.client.sent[0][1])

    def test_foreign_private_or_group_message_is_ignored(self):
        self.tg.client.updates = [
            update(21, 222, 222, "جيجي شو وضع الذهب"),
            update(22, 111, -999, "جيجي شو وضع الذهب", "group"),
        ]
        self.tg.poll()
        self.assertEqual(self.tg.client.sent, [])

    def test_private_commands_do_not_modify_group_or_orders(self):
        self.tg.client.updates = [update(23, 111, 111, "/menu"),
                                  update(24, 111, 111, "جيجي وقف التداول")]
        self.tg.poll()
        self.assertEqual(len(self.tg.client.sent), 2)
        self.assertIsNone(self.store.get("v4_telegram_group_id"))
        self.assertIsNone(self.store.get("v4_active"))
        self.assertEqual(self.store.get("v4_telegram_update_offset"), 25)


if __name__ == "__main__":
    unittest.main()
