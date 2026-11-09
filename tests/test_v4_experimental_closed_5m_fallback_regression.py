"""Fail-closed regression tests for the experimental Laith 5m quote fallback.

No live broker orders, API keys or Telegram sends are involved.
"""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from market import DataError
from v4_group_runtime import _shared_quick_entry_reference


class ClosedFiveMinuteReferenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 9, 14, 45, 0, tzinfo=timezone.utc)
        self.market = Mock()
        self.market.current_candle_reference.side_effect = DataError("market_quote_stale")

    def bar(self, age):
        end = self.now - timedelta(seconds=age)
        return SimpleNamespace(start=end - timedelta(minutes=5), end=end,
                               open=100.0, high=102.0, low=99.0, close=101.0)

    def test_recent_closed_bar_is_marked_delayed_not_live(self):
        result = _shared_quick_entry_reference(self.market, [self.bar(30)], self.now)
        self.assertEqual(result["price"], 101.0)
        self.assertTrue(result["delayed_reference"])
        self.assertFalse(result["current_five_minute_candle"])
        self.assertEqual(result["entry_delay_seconds"], 30.0)

    def test_exact_ninety_seconds_is_last_allowed_fallback(self):
        result = _shared_quick_entry_reference(self.market, [self.bar(90)], self.now)
        self.assertEqual(result["entry_delay_seconds"], 90.0)

    def test_older_than_ninety_seconds_fails_closed(self):
        with self.assertRaises(DataError):
            _shared_quick_entry_reference(self.market, [self.bar(91)], self.now)

    def test_future_closed_bar_fails_closed(self):
        with self.assertRaises(DataError):
            _shared_quick_entry_reference(self.market, [self.bar(-1)], self.now)

    def test_no_bars_does_not_invent_quote(self):
        with self.assertRaises(DataError):
            _shared_quick_entry_reference(self.market, [], self.now)

    def test_valid_live_reference_is_not_replaced(self):
        live = {"price": 103.0, "source": "live"}
        self.market.current_candle_reference.side_effect = None
        self.market.current_candle_reference.return_value = live
        self.assertIs(_shared_quick_entry_reference(self.market, [self.bar(91)], self.now), live)


if __name__ == "__main__":
    unittest.main()
