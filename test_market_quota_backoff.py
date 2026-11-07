"""Regression tests for safe Twelve Data rate-limit handling."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from market import Market, DataError


class MarketQuotaTests(unittest.TestCase):
    def test_http_429_enters_cooldown_without_repeat_requests(self):
        session = Mock()
        session.get.return_value.status_code = 429
        market = Market("fake", session=session)
        now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        with patch("market.time.monotonic", return_value=1000.0):
            with self.assertRaisesRegex(DataError, "market_quota_cooldown"):
                market.fetch(now)
        with patch("market.time.monotonic", return_value=1001.0):
            with self.assertRaisesRegex(DataError, "market_quota_cooldown"):
                market.fetch(now)
        self.assertEqual(session.get.call_count, 1)

    def test_cache_does_not_bypass_freshness_check(self):
        from market import Bar
        market = Market("fake", session=Mock())
        market._bars_cache = [Bar(datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc), 4000, 4001, 3999, 4000)]
        market._bars_cache_at = 1000.0
        with patch("market.time.monotonic", return_value=1001.0):
            with self.assertRaisesRegex(DataError, "market_closed_candles_stale"):
                market.fetch(datetime(2026, 11, 6, 12, tzinfo=timezone.utc))
        market.session.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
