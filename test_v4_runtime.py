from datetime import datetime, timedelta, timezone
import unittest

from market import Bar, DataError
from v4_runtime import (
    calibrate_quick_strength,
    quick_history_snapshot,
    quick_market_bars,
    quick_reference_quote,
)

UTC = timezone.utc


class FakeMarket:
    def __init__(self, error=None, quote=None, bars=None, fetch_error=None):
        self.error = error
        self._quote = quote
        self._bars = bars
        self.fetch_error = fetch_error

    def quote(self, clock):
        if self.error:
            raise DataError(self.error)
        return dict(self._quote)

    def fetch(self, now):
        if self.fetch_error:
            raise DataError(self.fetch_error)
        return list(self._bars or [])


class V4RuntimeTests(unittest.TestCase):
    def test_prefers_fresh_provider_quote(self):
        now = datetime(2026, 9, 16, 20, 10, tzinfo=UTC)
        bars = [Bar(now - timedelta(minutes=5), 4300, 4302, 4299, 4301, 5)]
        q = quick_reference_quote(FakeMarket(quote={"price": 4302.0, "time": now.timestamp(), "source": "Twelve Data"}), bars, now)
        self.assertEqual(q["price"], 4302.0)
        self.assertFalse(q["delayed_reference"])

    def test_stale_quote_falls_back_to_last_closed_bar(self):
        now = datetime(2026, 9, 16, 20, 10, tzinfo=UTC)
        bars = [Bar(now - timedelta(minutes=5), 4300, 4302, 4299, 4301, 5)]
        q = quick_reference_quote(FakeMarket(error="market_quote_stale"), bars, now)
        self.assertEqual(q["price"], 4301.0)
        self.assertTrue(q["delayed_reference"])
        self.assertEqual(q["source"], "آخر شمعة 5د مغلقة")

    def test_rate_limited_quote_falls_back_to_last_closed_bar(self):
        now = datetime(2026, 9, 16, 22, 10, tzinfo=UTC)
        bars = [Bar(now - timedelta(minutes=5), 4300, 4302, 4299, 4301, 5)]
        q = quick_reference_quote(FakeMarket(error="market_http_429"), bars, now)
        self.assertEqual(q["price"], 4301.0)
        self.assertTrue(q["delayed_reference"])

    def test_rate_limited_bars_use_fresh_cache(self):
        now = datetime(2026, 9, 16, 22, 10, tzinfo=UTC)
        cached = [Bar(now - timedelta(minutes=5), 4300, 4302, 4299, 4301, 5)]
        bars, reused = quick_market_bars(FakeMarket(fetch_error="market_http_429"), now, cached)
        self.assertTrue(reused)
        self.assertEqual(bars[-1].close, 4301)

    def test_connection_failure_bars_use_fresh_cache(self):
        now = datetime(2026, 9, 16, 22, 10, tzinfo=UTC)
        cached = [Bar(now - timedelta(minutes=5), 4300, 4302, 4299, 4301, 5)]
        bars, reused = quick_market_bars(FakeMarket(fetch_error="market_connection_failed"), now, cached)
        self.assertTrue(reused)
        self.assertEqual(bars[-1].close, 4301)

    def test_rate_limited_bars_without_cache_still_fail(self):
        now = datetime(2026, 9, 16, 22, 10, tzinfo=UTC)
        with self.assertRaises(DataError):
            quick_market_bars(FakeMarket(fetch_error="market_http_429"), now, None)

    def test_unrelated_quote_error_is_not_hidden(self):
        now = datetime(2026, 9, 16, 20, 10, tzinfo=UTC)
        bars = [Bar(now - timedelta(minutes=5), 4300, 4302, 4299, 4301, 5)]
        with self.assertRaises(DataError):
            quick_reference_quote(FakeMarket(error="market_quote_invalid"), bars, now)

    def test_quick_history_snapshot_uses_only_measured_closed_results(self):
        history = quick_history_snapshot([
            {"status": "closed", "r": 1.5},
            {"status": "closed", "r": 0.4},
            {"status": "closed", "r": -1.0},
            {"status": "closed", "r": 0.0},
            {"status": "closed", "r": None},
            {"status": "active", "r": 1.5},
        ])
        self.assertEqual(history["sample"], 4)
        self.assertEqual(history["positive"], 2)
        self.assertEqual(history["negative"], 1)
        self.assertEqual(history["flat"], 1)
        self.assertEqual(history["positive_rate"], 50)

    def test_strong_is_downgraded_when_risk_is_high(self):
        setup = {"strength": "قوية", "risk_level": "مرتفعة"}
        calibrated = calibrate_quick_strength(setup, {"side": "BUY"})
        self.assertEqual(calibrated["raw_strength"], "قوية")
        self.assertEqual(calibrated["strength"], "متوسطة")
        self.assertIn("المخاطرة مرتفعة", calibrated["strength_adjustments"])
        self.assertFalse(calibrated["strength_is_probability"])

    def test_strong_is_downgraded_when_higher_timeframe_is_wait(self):
        setup = {"strength": "قوية", "risk_level": "منخفضة"}
        calibrated = calibrate_quick_strength(setup, {"side": "WAIT"})
        self.assertEqual(calibrated["strength"], "متوسطة")
        self.assertIn("الاتجاه الأكبر غير مؤكد", calibrated["strength_adjustments"])

    def test_strong_remains_strong_when_risk_is_not_high_and_higher_confirms(self):
        setup = {"strength": "قوية", "risk_level": "متوسطة"}
        calibrated = calibrate_quick_strength(setup, {"side": "BUY"})
        self.assertEqual(calibrated["strength"], "قوية")
        self.assertEqual(calibrated["strength_adjustments"], [])


if __name__ == "__main__":
    unittest.main()
