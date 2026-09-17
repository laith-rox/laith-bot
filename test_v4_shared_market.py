from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from market import Bar, DataError
from v4_shared_market import SharedV4Market, closed_bar_reference

UTC = timezone.utc


class V4SharedMarketTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 17, 12, 0, 12, tzinfo=UTC)
        self.bars = [
            Bar(
                datetime(2026, 9, 17, 11, 55, tzinfo=UTC),
                4300.0,
                4303.0,
                4299.0,
                4302.0,
                5,
            )
        ]
        self.current = Bar(
            datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
            4302.2,
            4303.4,
            4301.8,
            4302.9,
            5,
        )

    def test_same_five_minute_slot_reuses_one_provider_fetch(self):
        market = SharedV4Market("dummy")
        with patch.object(market, "_fetch_provider_snapshot", return_value=(self.bars, self.current)) as provider_fetch:
            first = market.fetch(self.now)
            second = market.fetch(self.now + timedelta(seconds=30))
        self.assertEqual(first, self.bars)
        self.assertEqual(second, self.bars)
        self.assertEqual(provider_fetch.call_count, 1)
        self.assertEqual(market.provider_fetches, 1)
        self.assertEqual(market.cache_hits, 1)

    def test_new_five_minute_slot_fetches_once_again(self):
        market = SharedV4Market("dummy")
        next_current = Bar(
            datetime(2026, 9, 17, 12, 5, tzinfo=UTC),
            4303.0, 4304.0, 4302.0, 4303.5, 5,
        )
        with patch.object(
            market,
            "_fetch_provider_snapshot",
            side_effect=[(self.bars, self.current), (self.bars, next_current)],
        ) as provider_fetch:
            market.fetch(self.now)
            market.fetch(self.now + timedelta(minutes=5))
        self.assertEqual(provider_fetch.call_count, 2)
        self.assertEqual(market.provider_fetches, 2)

    def test_quick_reference_uses_latest_closed_bar_for_monitoring(self):
        reference = closed_bar_reference(self.bars, self.now)
        self.assertEqual(reference["price"], 4302.0)
        self.assertTrue(reference["shared_candle_reference"])
        self.assertFalse(reference["delayed_reference"])
        self.assertIn("V4", reference["source"])

    def test_current_candle_reference_matches_slot_and_uses_live_observed_price(self):
        market = SharedV4Market("dummy")
        with patch.object(market, "_fetch_provider_snapshot", return_value=(self.bars, self.current)):
            market.fetch(self.now)
            reference = market.current_candle_reference(self.now)
        self.assertEqual(reference["price"], 4302.9)
        self.assertEqual(reference["candle_open"], 4302.2)
        self.assertEqual(reference["candle_start"], self.current.start.timestamp())
        self.assertEqual(reference["entry_delay_seconds"], 12.0)
        self.assertTrue(reference["current_five_minute_candle"])
        self.assertTrue(reference["timing_aligned"])
        self.assertFalse(reference["candle_open_estimated"])

    def test_current_candle_reference_rejects_late_entry(self):
        market = SharedV4Market("dummy")
        with patch.object(market, "_fetch_provider_snapshot", return_value=(self.bars, self.current)):
            market.fetch(self.now)
            with self.assertRaisesRegex(DataError, "quick_candle_entry_window_missed"):
                market.current_candle_reference(self.now + timedelta(seconds=70))

    def test_missing_current_candle_uses_current_slot_live_quote(self):
        market = SharedV4Market("dummy")
        quote_stamp = self.now.timestamp() - 2
        with patch.object(market, "_fetch_provider_snapshot", return_value=(self.bars, None)), \
             patch.object(market, "quote", return_value={"price": 4302.7, "time": quote_stamp, "source": "Twelve Data"}):
            market.fetch(self.now)
            reference = market.current_candle_reference(self.now)
        self.assertEqual(reference["price"], 4302.7)
        self.assertEqual(reference["candle_open"], 4302.0)
        self.assertTrue(reference["candle_open_estimated"])
        self.assertTrue(reference["timing_aligned"])
        self.assertEqual(reference["candle_start"], datetime(2026, 9, 17, 12, 0, tzinfo=UTC).timestamp())
        self.assertIn("live quote", reference["source"])

    def test_live_quote_fallback_rejects_quote_from_previous_slot(self):
        market = SharedV4Market("dummy")
        stale_slot_stamp = datetime(2026, 9, 17, 11, 59, 50, tzinfo=UTC).timestamp()
        with patch.object(market, "_fetch_provider_snapshot", return_value=(self.bars, None)), \
             patch.object(market, "quote", return_value={"price": 4302.7, "time": stale_slot_stamp, "source": "Twelve Data"}):
            market.fetch(self.now)
            with self.assertRaisesRegex(DataError, "quick_live_quote_not_in_current_slot"):
                market.current_candle_reference(self.now)


if __name__ == "__main__":
    unittest.main()
