"""Safe offline regression tests for manual BTC Telegram alerts (no network)."""
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from market import DataError
from v4_bitcoin_signals import (
    BitcoinSignalPublisher, _aggregate, _bars, _message,
)
from market import Bar

UTC = timezone.utc


class StoreStub:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class TelegramStub:
    def __init__(self, successful=True):
        self.messages = []
        self.successful = successful

    def send(self, value):
        self.messages.append(value)
        return self.successful


SIGNAL = {
    "status": "SIGNAL", "side": "BUY", "score": 6,
    "entry": 100000., "sl": 99700., "tp1": 100400., "tp2": 100650.,
}


class BitcoinSignalsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 10, 30, tzinfo=UTC)
        self.store = StoreStub()
        self.telegram = TelegramStub()
        self.publisher = BitcoinSignalPublisher(self.store, self.telegram, provider=object())

    def test_candle_validation_rejects_wrong_price_order(self):
        with self.assertRaises(DataError):
            _bars([[self.now.timestamp() - 600, 100, 90, 95, 96, 2]], 5, self.now)

    def test_current_open_candle_is_not_used_as_closed(self):
        epoch = int(self.now.timestamp() // 300) * 300
        rows = [
            [epoch, 90, 110, 100, 105, 1],
            [epoch - 300, 90, 110, 100, 105, 1],
        ]
        result = _bars(rows, 5, self.now + timedelta(seconds=30))
        self.assertEqual(len(result), 1)
        self.assertEqual(int(result[-1].start.timestamp()), epoch - 300)

    def test_aggregation_refuses_gaps(self):
        first = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
        rows = [
            Bar(first, 100, 110, 90, 105),
            Bar(first + timedelta(minutes=10), 105, 111, 100, 107),
        ]
        self.assertEqual(_aggregate(rows, 15), [])

    def test_manual_alert_is_telegram_only_and_deduplicated(self):
        with patch("v4_bitcoin_signals.analyze_btc", return_value=SIGNAL) as model:
            self.assertEqual(self.publisher.cycle(self.now), "sent")
            self.assertEqual(self.publisher.cycle(self.now), "already_sent")
        model.assert_called_once()
        self.assertEqual(len(self.telegram.messages), 1)
        self.assertIn("BTC/USD", self.telegram.messages[0])
        self.assertIn("بدون فتح صفقات", self.telegram.messages[0])

    def test_quarterly_weak_reports_are_no_entry_and_deduped(self):
        state = {"status": "WAIT", "reason": "h1_h4_not_aligned",
                 "h1_trend": "WAIT", "h4_trend": "SELL"}
        preview = {"side": "SELL", "score": 2, "price": 100000.,
                   "sl": 101500., "tp1": 97300., "tp2": 95800.}
        import os
        with patch.dict(os.environ, {"V4_BTC_QUARTERLY_REPORTS_ENABLED": "1"}), \
             patch("v4_bitcoin_signals.analyze_btc", return_value=state), \
             patch("v4_bitcoin_signals.weak_preview", return_value=preview):
            self.assertEqual(self.publisher.cycle(self.now), "weak_sent")
            self.assertEqual(self.publisher.cycle(self.now), "already_sent")
        self.assertEqual(len(self.telegram.messages), 1)
        msg = self.telegram.messages[0]
        self.assertIn("لا تدخل الآن", msg)
        self.assertIn("ضعيفة", msg)
        self.assertIn("100,000.00", msg)
        self.assertIn("وقف افتراضي", msg)
        self.assertTrue(self.store.get("v4_btc_quarterly_last")["no_entry"])
        self.assertIsNone(self.store.get("v4_btc_last_sent_slot"))
        self.assertIsNone(self.store.get("v4_btc_observed_active"))
        self.assertIsNone(self.store.get("v4_btc_observed_journal"))

    def test_no_data_still_reports_no_entry_without_price(self):
        import os
        with patch.dict(os.environ, {"V4_BTC_QUARTERLY_REPORTS_ENABLED": "1"}), \
             patch("v4_bitcoin_signals.analyze_btc", side_effect=DataError("btc_quote_stale")):
            self.assertEqual(self.publisher.cycle(self.now), "weak_sent")
        self.assertIn("لا تدخل الآن", self.telegram.messages[0])
        self.assertIn("غير معروضة", self.telegram.messages[0])
        self.assertNotIn("100,000.00", self.telegram.messages[0])
        self.assertIsNone(self.store.get("v4_btc_observed_active"))

    def test_weak_send_failure_does_not_lock_slot(self):
        import os
        state = {"status": "WAIT", "reason": "h1_h4_not_aligned"}
        self.telegram.successful = False
        with patch.dict(os.environ, {"V4_BTC_QUARTERLY_REPORTS_ENABLED": "1"}), \
             patch("v4_bitcoin_signals.analyze_btc", return_value=state):
            self.assertEqual(self.publisher.cycle(self.now), "undelivered")
        self.assertIsNone(self.store.get("v4_btc_quarterly_last_slot"))

    def test_cooldown_gets_no_entry_card_not_fake_weak_trade(self):
        import os
        self.store.set("v4_btc_last_sent_side", "BUY")
        self.store.set("v4_btc_last_sent_at", self.now.timestamp() - 1200)
        with patch.dict(os.environ, {"V4_BTC_QUARTERLY_REPORTS_ENABLED": "1"}), \
             patch("v4_bitcoin_signals.analyze_btc", return_value=SIGNAL):
            self.assertEqual(self.publisher.cycle(self.now), "weak_sent")
        self.assertIn("فترة التهدئة", self.telegram.messages[0])
        self.assertIn("لا تدخل الآن", self.telegram.messages[0])
        self.assertIsNone(self.store.get("v4_btc_observed_active"))
        self.assertEqual(self.store.get("v4_btc_last_sent_side"), "BUY")

    def test_strong_alert_stays_separate_in_quarterly_mode(self):
        import os
        with patch.dict(os.environ, {"V4_BTC_QUARTERLY_REPORTS_ENABLED": "1"}), \
             patch("v4_bitcoin_signals.analyze_btc", return_value=SIGNAL):
            self.assertEqual(self.publisher.cycle(self.now), "sent")
            self.assertEqual(self.publisher.cycle(self.now), "already_sent")
        self.assertIn("إشارة بيتكوين مستقلة", self.telegram.messages[0])
        self.assertNotIn("ضعيفة", self.telegram.messages[0])
        self.assertEqual(len(self.telegram.messages), 1)

    def test_no_alert_on_unconfirmed_setup(self):
        with patch("v4_bitcoin_signals.analyze_btc", return_value={"status": "WAIT", "reason": "h1_h4_not_aligned"}):
            self.assertEqual(self.publisher.cycle(self.now), "wait")
        self.assertEqual(self.telegram.messages, [])

    def test_provider_failure_never_sends(self):
        with patch("v4_bitcoin_signals.analyze_btc", side_effect=DataError("btc_quote_stale")):
            self.assertEqual(self.publisher.cycle(self.now), "wait_data")
        self.assertEqual(self.telegram.messages, [])
        self.assertEqual(self.store.get("v4_btc_status")["status"], "WAIT_DATA")

    def test_failed_send_does_not_mark_success(self):
        self.telegram.successful = False
        with patch("v4_bitcoin_signals.analyze_btc", return_value=SIGNAL):
            self.assertEqual(self.publisher.cycle(self.now), "undelivered")
        self.assertIsNone(self.store.get("v4_btc_last_sent_slot"))

    def test_cooldown_for_same_direction(self):
        self.store.set("v4_btc_last_sent_side", "BUY")
        self.store.set("v4_btc_last_sent_at", self.now.timestamp() - 20 * 60)
        with patch("v4_bitcoin_signals.analyze_btc", return_value=SIGNAL):
            self.assertEqual(self.publisher.cycle(self.now), "cooldown")
        self.assertEqual(self.telegram.messages, [])

    def test_works_on_sunday(self):
        self.assertEqual(self.now.weekday(), 6)
        with patch("v4_bitcoin_signals.analyze_btc", return_value=SIGNAL):
            self.assertEqual(self.publisher.cycle(self.now), "sent")
        self.assertEqual(len(self.telegram.messages), 1)


if __name__ == "__main__":
    unittest.main()
