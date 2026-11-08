"""M5 BTC evening Telegram lane: deterministic offline safety tests, no orders."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from market import Bar, DataError
from v4_btc_m5_quick import BTCQuickPublisher, analyze_quick, in_quick_window

UTC = timezone.utc
LOCAL = ZoneInfo("Asia/Hebron")


class Provider:
    def __init__(self, now, side="BUY", bad_ticker=False, bad_spread=False):
        # 120 strictly closed 5m bars, ending at local 19:00.
        final_start = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
        self.bars = []
        for i in range(120):
            start = final_start - timedelta(minutes=5 * (119 - i))
            base = 100000 + i * (10 if side == "BUY" else -10)
            opened = float(base)
            if side == "BUY":
                bar = Bar(start, opened, opened + 23, opened - 10, opened + 18, 5)
            else:
                bar = Bar(start, opened, opened + 10, opened - 23, opened - 18, 5)
            self.bars.append(bar)
        self.last_volumes = [100.0] * 120
        self.bad_ticker = bad_ticker
        self.bad_spread = bad_spread

    def candles(self, now, minutes):
        assert minutes == 5
        return self.bars

    def ticker(self, now):
        if self.bad_ticker:
            raise DataError("btc_quote_stale")
        return self.bars[-1].close

    def book(self):
        p = self.bars[-1].close
        gap = 200 if self.bad_spread else 2
        return {"bids": [[str(p - gap), "3"]],
                "asks": [[str(p + gap), "3"]]}


class Store:
    def __init__(self):
        self.values = {}
    def get(self, key, default=None):
        return self.values.get(key, default)
    def set(self, key, value):
        self.values[key] = value


class Telegram:
    def __init__(self, works=True):
        self.sent = []
        self.works = works
    def send(self, message):
        if self.works:
            self.sent.append(message)
        return self.works


class M5QuickTests(unittest.TestCase):
    def setUp(self):
        # 17:00 UTC == 19:00 Palestine on November 8, 2026.
        self.now = datetime(2026, 11, 8, 17, 0, 30, tzinfo=UTC)
        self.telegram = Telegram()
        self.store = Store()

    def test_hours_19_inclusive_23_exclusive_and_weekend(self):
        self.assertTrue(in_quick_window(self.now))
        self.assertFalse(in_quick_window(self.now - timedelta(minutes=1)))
        self.assertTrue(in_quick_window(self.now + timedelta(hours=3, minutes=59)))
        self.assertFalse(in_quick_window(self.now + timedelta(hours=4)))
        self.assertEqual(self.now.weekday(), 6)

    def test_qualified_bullish_signal(self):
        with patch("v4_btc_m5_quick.rsi", return_value=61):
            result = analyze_quick(self.now, Provider(self.now, "BUY"))
        self.assertEqual(result["status"], "SIGNAL")
        self.assertEqual(result["side"], "BUY")
        self.assertEqual(result["score"], 6)
        self.assertLess(result["sl"], result["entry"])
        self.assertGreater(result["tp1"], result["entry"])
        self.assertLess(result["spread_bps"], 8)
        self.assertTrue(result["candle_end"].startswith("2026-11-08T17:00:00"))

    def test_qualified_bearish_signal_without_h4_gate(self):
        with patch("v4_btc_m5_quick.rsi", return_value=39):
            result = analyze_quick(self.now, Provider(self.now, "SELL"))
        self.assertEqual(result["status"], "SIGNAL")
        self.assertEqual(result["side"], "SELL")
        self.assertGreater(result["sl"], result["entry"])
        self.assertLess(result["tp1"], result["entry"])

    def test_stale_candle_fails_closed(self):
        provider = Provider(self.now, "BUY")
        provider.bars = [
            Bar(b.start - timedelta(minutes=10), b.open, b.high, b.low, b.close, 5)
            for b in provider.bars
        ]
        with self.assertRaisesRegex(DataError, "btc_quick_candle_stale"):
            analyze_quick(self.now, provider)

    def test_missing_volume_fails_closed(self):
        provider = Provider(self.now, "BUY")
        provider.last_volumes = None
        with self.assertRaises(DataError):
            analyze_quick(self.now, provider)

    def test_broad_spread_blocks_signal(self):
        provider = Provider(self.now, "BUY", bad_spread=True)
        with patch("v4_btc_m5_quick.rsi", return_value=61):
            result = analyze_quick(self.now, provider)
        self.assertEqual(result["status"], "WAIT")
        self.assertEqual(result["reason"], "btc_quick_spread_wide")

    def test_old_or_bad_quote_never_sends(self):
        provider = Provider(self.now, "BUY", bad_ticker=True)
        runner = BTCQuickPublisher(self.store, self.telegram, provider)
        with patch("v4_btc_m5_quick.rsi", return_value=61):
            self.assertEqual(runner.cycle(self.now), "wait")
        self.assertEqual(self.telegram.sent, [])
        self.assertEqual(self.store.get("v4_btc_quick_status")["status"], "WAIT_DATA")

    def test_independent_5m_signal_and_cooldown(self):
        provider = Provider(self.now, "BUY")
        runner = BTCQuickPublisher(self.store, self.telegram, provider)
        with patch("v4_btc_m5_quick.rsi", return_value=61):
            self.assertEqual(runner.cycle(self.now), "sent")
            self.assertEqual(runner.cycle(self.now), "already_checked")
            self.assertEqual(runner.cycle(self.now + timedelta(minutes=5)), "cooldown")
        self.assertEqual(len(self.telegram.sent), 1)
        self.assertIn("إشارة سريعة M5", self.telegram.sent[0])
        self.assertIn("وقف مرجعي", self.telegram.sent[0])
        self.assertIn("فلسطين", self.telegram.sent[0])
        self.assertIsNone(self.store.get("v4_btc_observed_active"))
        self.assertIsNone(self.store.get("v4_btc_last_sent_slot"))
        self.assertIsNone(self.store.get("v4_active"))

    def test_outside_hours_no_api_calls_or_signal(self):
        class MustNotCall:
            def candles(self, *args):
                raise AssertionError("should not fetch candles outside window")
        runner = BTCQuickPublisher(self.store, self.telegram, MustNotCall())
        self.assertEqual(runner.cycle(self.now - timedelta(minutes=1)), "outside_hours")
        self.assertEqual(self.telegram.sent, [])
        self.assertEqual(self.store.get("v4_btc_quick_status")["status"], "CLOSED")

    def test_rejected_rsi_never_sends_trade(self):
        provider = Provider(self.now, "BUY")
        runner = BTCQuickPublisher(self.store, self.telegram, provider)
        with patch("v4_btc_m5_quick.rsi", return_value=91):
            self.assertEqual(runner.cycle(self.now), "wait")
        self.assertEqual(self.telegram.sent, [])
        self.assertEqual(self.store.get("v4_btc_quick_status")["status"], "WAIT")

    def test_failed_telegram_delivery_does_not_claim_sent(self):
        runner = BTCQuickPublisher(self.store, Telegram(works=False), Provider(self.now))
        with patch("v4_btc_m5_quick.rsi", return_value=61):
            self.assertEqual(runner.cycle(self.now), "undelivered")
        self.assertIsNone(self.store.get("v4_btc_quick_last_sent_slot"))


if __name__ == "__main__":
    unittest.main()
