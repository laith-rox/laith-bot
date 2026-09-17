from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from market import Bar
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

    def test_same_five_minute_slot_reuses_one_provider_fetch(self):
        market = SharedV4Market("dummy")
        with patch("v4_shared_market.Market.fetch", return_value=self.bars) as provider_fetch:
            first = market.fetch(self.now)
            second = market.fetch(self.now + timedelta(seconds=30))
        self.assertEqual(first, self.bars)
        self.assertEqual(second, self.bars)
        self.assertEqual(provider_fetch.call_count, 1)
        self.assertEqual(market.provider_fetches, 1)
        self.assertEqual(market.cache_hits, 1)

    def test_new_five_minute_slot_fetches_once_again(self):
        market = SharedV4Market("dummy")
        with patch("v4_shared_market.Market.fetch", return_value=self.bars) as provider_fetch:
            market.fetch(self.now)
            market.fetch(self.now + timedelta(minutes=5))
        self.assertEqual(provider_fetch.call_count, 2)
        self.assertEqual(market.provider_fetches, 2)

    def test_quick_reference_uses_latest_closed_bar_without_quote_call(self):
        reference = closed_bar_reference(self.bars, self.now)
        self.assertEqual(reference["price"], 4302.0)
        self.assertTrue(reference["shared_candle_reference"])
        self.assertFalse(reference["delayed_reference"])
        self.assertIn("V4", reference["source"])


if __name__ == "__main__":
    unittest.main()
