"""Offline BTC weak-quarterly cards: research only, never broker orders."""
import unittest
from datetime import datetime, timedelta, timezone

from market import Bar, DataError
from v4_bitcoin_signals import _aggregate
from v4_btc_quarterly import weak_preview, quarterly_message

UTC = timezone.utc


class MarketStub:
    def __init__(self, now, live=True):
        final_start = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
        self.bars = []
        for i in range(180):
            start = final_start - timedelta(minutes=5 * (179 - i))
            opened = 100000. + i
            self.bars.append(
                Bar(start, opened, opened + 100., opened - 100., opened + 50., 5)
            )
        self.live = live
        self.last_5m_bars = self.bars

    def candles(self, now, interval):
        if interval != 5:
            raise AssertionError("BTC quarterly should not request other interval")
        return self.bars

    def ticker(self, now):
        if not self.live:
            raise DataError("btc_quote_stale")
        return self.bars[-1].close


class WeakQuarterlyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 8, 10, 30, 25, tzinfo=UTC)
        self.provider = MarketStub(self.now)
        self.wait = {
            "status": "WAIT", "reason": "h1_h4_not_aligned",
            "h1_trend": "WAIT", "h4_trend": "SELL",
            "time": self.now.isoformat(),
        }

    def test_weak_sell_proposes_hypothetical_levels_not_real_signal(self):
        result = weak_preview(self.now, self.provider, self.wait, _aggregate)
        self.assertEqual(result["side"], "SELL")
        self.assertIsInstance(result["score"], int)
        self.assertLess(result["score"], 7)
        self.assertGreater(result["sl"], result["price"])
        self.assertLess(result["tp1"], result["price"])
        card = quarterly_message(self.now, self.wait, result)
        self.assertIn("لا تدخل الآن", card)
        self.assertIn("صفقة ضعيفة", card)
        self.assertIn("افتراضي", card)
        self.assertIn("وقف افتراضي", card)
        self.assertIn("JustMarkets", card)

    def test_bad_spot_quote_hides_all_levels(self):
        result = weak_preview(self.now, MarketStub(self.now, live=False), self.wait, _aggregate)
        self.assertIsNone(result["price"])
        card = quarterly_message(self.now, self.wait, result)
        self.assertIn("غير معروضة", card)
        self.assertNotIn("وقف افتراضي", card)

    def test_unverified_data_hides_levels_even_when_candles_look_good(self):
        result = weak_preview(self.now, self.provider, {
            "status": "WAIT_DATA", "reason": "btc_quote_stale",
        }, _aggregate)
        self.assertEqual(result["side"], "WAIT")
        self.assertIsNone(result["price"])
        self.assertIn("غير معروضة", quarterly_message(self.now, {"status": "WAIT_DATA"}, result))

    def test_existing_confirmed_signal_in_cooldown_is_not_called_weak(self):
        card = quarterly_message(self.now, {
            "status": "SIGNAL", "score": 6,
            "h1_trend": "BUY", "h4_trend": "BUY",
        }, {"side": "BUY", "score": 6, "price": None}, note="cooldown")
        self.assertIn("فرصة مكررة", card)
        self.assertIn("لا تدخل الآن", card)
        self.assertNotIn("صفقة ضعيفة", card)

    def test_future_candle_is_not_accepted(self):
        self.provider.last_5m_bars = [
            Bar(self.now + timedelta(minutes=5 * i), 100, 110, 90, 105, 5)
            for i in range(70)
        ]
        self.provider.bars = self.provider.last_5m_bars
        result = weak_preview(self.now, self.provider, self.wait, _aggregate)
        self.assertIsNone(result["price"])
        self.assertEqual(result["side"], "WAIT")


if __name__ == "__main__":
    unittest.main()
