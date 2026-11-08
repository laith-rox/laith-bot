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
