"""V4 follow-through safety: features 21, 22, 23 and 26."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from market import Bar
from v4_opportunity_followthrough import (
    audit_quick_excursion, record_opportunity, record_telegram_delivery,
    remember_watch, transition_message,
)
from v4_quick import advance_quick
from v4_quick_balance import quick_message as balanced_message
from v4_group_telegram import V4Telegram

UTC = timezone.utc
T = datetime(2026, 11, 10, 21, 0, tzinfo=UTC)


class Store:
    def __init__(self):
        self.data = {}
    def get(self, key, default=None):
        return self.data.get(key, default)
    def set(self, key, value):
        self.data[key] = value


def bar(minutes, high, low, close=100):
    start = T + timedelta(minutes=minutes)
    return Bar(start, 100, high, low, close, 5)


class FollowThroughTests(unittest.TestCase):
    def test_21_22_promote_watch_once_without_changing_policy(self):
        store = Store()
        self.assertIsNone(record_opportunity(store, "BUY", "WATCH", T, score=4))
        event = record_opportunity(store, "BUY", "CAUTIOUS", T + timedelta(minutes=5), score=5)
        self.assertEqual(event["transition"], "WATCH_TO_CAUTIOUS")
        self.assertIn("ادخل بحذر", transition_message(event))
        self.assertIsNone(record_opportunity(store, "BUY", "CAUTIOUS",
                                             T + timedelta(minutes=10), score=5))
        event2 = record_opportunity(store, "BUY", "ENTER_NOW", T + timedelta(minutes=15), score=6)
        self.assertEqual(event2["transition"], "CAUTIOUS_TO_ENTER_NOW")
        self.assertEqual(len(store.get("v4_opportunity_transitions")), 2)

    def test_21_no_false_cross_direction_promotion(self):
        store = Store()
        record_opportunity(store, "BUY", "WATCH", T, score=4)
        self.assertIsNone(record_opportunity(store, "SELL", "ENTER_NOW", T+timedelta(minutes=5)))
        self.assertIsNone(record_opportunity(store, "BUY", "ENTER_NOW", T+timedelta(hours=1)))
        self.assertEqual(store.get("v4_opportunity_transitions"), None)

    def test_21_remember_wait_only_for_observable_side(self):
        store = Store()
        self.assertIsNone(remember_watch(store, {"side":"WAIT", "buy":3, "sell":3}, T))
        self.assertIsNone(store.get("v4_opportunity_progress"))
        remember_watch(store, {"side":"WAIT", "buy":5, "sell":2}, T)
        self.assertEqual(store.get("v4_opportunity_progress")["BUY"]["action"], "WATCH")

    def test_22_only_annotates_existing_quick_card(self):
        message = balanced_message({
            "id":"q1", "side":"BUY", "score":6, "total":7, "entry":4100.0,
            "stop":4098.0, "target":4103.0, "strength":"قوية",
            "risk_level":"منخفضة", "risk_reasons":[], "rsi":58.0,
            "created":T.timestamp(), "status":"active",
            "opportunity_transition":{"transition":"WATCH_TO_ENTER_NOW"},
        })
        self.assertIn("🔔 تحديث الفرصة:", message)
        self.assertIn("مراقبة ← ادخل الآن", message)

    def test_23_acked_delivery_is_not_same_as_attempt(self):
        s = Store()
        self.assertFalse(record_telegram_delivery(s, SimpleNamespace(status="retry"), "group", T))
        self.assertFalse(record_telegram_delivery(s, SimpleNamespace(status="uncertain"), "group", T))
        self.assertTrue(record_telegram_delivery(s, SimpleNamespace(status="sent",message_id=100), "group", T))
        self.assertEqual(s.get("v4_telegram_delivery_counts"),
                         {"retry":1,"uncertain":1,"sent":1})
        self.assertFalse(s.get("v4_telegram_delivery_audit")[1]["acknowledged"])
        self.assertTrue(s.get("v4_telegram_delivery_last")["acknowledged"])
        self.assertNotIn("chat_id", s.get("v4_telegram_delivery_last"))

    def test_23_group_transport_audits_once_no_duplicate_retries(self):
        s = Store()
        s.set("v4_telegram_chat_id", "1234")
        s.set("v4_telegram_group_id", "-5678")
        tg = V4Telegram("fake", s)
        class Client:
            def __init__(self):
                self.calls = []
                self.chat_id = ""
            def send(self, message):
                self.calls.append(message)
                return SimpleNamespace(status="uncertain",message_id=None,error="telegram_delivery_unknown")
        fake = Client()
        tg.client = fake
        self.assertFalse(tg.send("signal"))
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(s.get("v4_telegram_delivery_counts")["uncertain"], 1)

    def test_26_tracks_excursion_in_r_not_dollars(self):
        original = {
            "status":"active","side":"BUY","entry":100.0,"risk":2.0,
            "stop":98.0,"target":103.0,"announced":T.timestamp(),
            "expires":(T+timedelta(minutes=20)).timestamp(),
            "last_end":None,"rr":1.5,
        }
        bars = [bar(0,101,99.5,100.5),bar(5,102,98.5,101.5)]
        u = advance_quick(original, bars[:1], T + timedelta(minutes=5))
        measured = audit_quick_excursion(original,u,bars[:1])
        self.assertEqual(measured["excursion"]["mfe_r"], 0.5)
        self.assertEqual(measured["excursion"]["mae_r"], 0.25)
        u2 = advance_quick(measured,bars, T+timedelta(minutes=10))
        m2 = audit_quick_excursion(measured,u2,bars)
        self.assertEqual(m2["excursion"]["mfe_r"], 1.0)
        self.assertEqual(m2["excursion"]["mae_r"], 0.75)
        self.assertEqual(m2["status"],"active")

    def test_26_stop_and_target_same_bar_keeps_uncertainty(self):
        trade={"status":"active","side":"SELL","entry":100.0,"risk":2.0,
               "stop":102.0,"target":97.0,"announced":T.timestamp(),
               "expires":(T+timedelta(minutes=20)).timestamp(),
               "last_end":None,"rr":1.5}
        bars=[bar(0,103,96)]
        u=advance_quick(trade,bars,T+timedelta(minutes=5))
        result=audit_quick_excursion(trade,u,bars)
        self.assertEqual(result["outcome"],"AMBIGUOUS")
        self.assertTrue(result["excursion"]["intrabar_order_unknown"])
        self.assertIsNone(result["r"])

    def test_26_ignores_future_candles_and_same_timestamp(self):
        trade={"status":"active","side":"BUY","entry":100.0,"risk":2.0,
               "stop":98.0,"target":103.0,"announced":T.timestamp(),
               "expires":(T+timedelta(minutes=20)).timestamp(),
               "last_end":None,"rr":1.5}
        first=bar(0,101,99)
        after=bar(5,500,0)
        u=advance_quick(trade,[first],T+timedelta(minutes=5))
        measured=audit_quick_excursion(trade,u,[first,after])
        self.assertEqual(measured["excursion"]["mfe_price_units"],1.0)
        self.assertEqual(measured["excursion"]["mae_price_units"],1.0)


if __name__ == "__main__":
    unittest.main()
