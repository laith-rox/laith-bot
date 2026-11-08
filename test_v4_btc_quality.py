"""Offline verification of BTC quality gates and lifecycle; no live accounts."""
import unittest
from datetime import datetime, timedelta, timezone

from market import Bar, DataError
from v4_btc_quality import (
    btc_session, check_book, detect_liquidity, derivatives_context,
    dynamic_risk, m5_sniper, volume_confirmation,
)
from v4_btc_followups import (
    follow_observation, start_observation, btc_status_message, btc_stats_message,
)

UTC = timezone.utc


class Store:
    def __init__(self):
        self.items = {}
    def get(self, k, default=None):
        return self.items.get(k, default)
    def set(self, k, v):
        self.items[k] = v


class Notifier:
    def __init__(self):
        self.items = []
    def send(self, message):
        self.items.append(message)
        return True


class Provider:
    def __init__(self, bars):
        self.bars = bars
    def candles(self, now, minutes):
        return self.bars


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.sun = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
        self.sat = self.sun - timedelta(days=1)
        self.start = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)

    def test_utc_weekend_open_for_btc(self):
        self.assertEqual(btc_session(self.sun), "WEEKEND")

    def test_fake_breakout_and_liquidity_sweep(self):
        bars = [Bar(self.start + timedelta(minutes=15*i), 95, 100, 90, 97, 15)
                for i in range(15)]
        bars[-1] = Bar(bars[-1].start, 96, 105, 95, 99, 15)
        self.assertTrue(detect_liquidity(bars, "BUY", 6)["fake_breakout"])
        bars[-1] = Bar(bars[-1].start, 91, 99, 86, 96, 15)
        outcome = detect_liquidity(bars, "BUY", 6)
        self.assertTrue(outcome["liquidity_sweep"])
        self.assertTrue(outcome["context_ok"])

    def test_volume_filters_weekend_and_bad_samples(self):
        self.assertFalse(volume_confirmation([100.]*21 + [105.], "WEEKEND")["ok"])
        self.assertTrue(volume_confirmation([100.]*21 + [125.], "WEEKEND")["ok"])
        self.assertEqual(volume_confirmation([None]*22, "WEEKEND")["reason"], "volume_invalid")

    def test_book_depth_spread_and_imbalance(self):
        book = {"bids": [["100000", "2"]], "asks": [["100002", "2"]]}
        result = check_book(book, "BUY")
        self.assertTrue(result["ok"])
        self.assertLess(result["spread_bps"], 1)
        book["asks"] = [["100100", "2"]]
        self.assertFalse(check_book(book, "BUY")["ok"])
        with self.assertRaises(DataError):
            check_book({"bids": [], "asks": []}, "BUY")

    def test_derivatives_missing_is_not_fake_zero(self):
        v = derivatives_context({"available": False}, "BUY", self.sun)
        self.assertFalse(v["available"])
        self.assertEqual(v["risk"], "UNVERIFIED")
        crowded = derivatives_context({
            "available": True, "funding": 0.0011,
            "open_interest": 110, "previous_open_interest": 100,
            "timestamp": self.sun.timestamp(),
        }, "BUY", self.sun)
        self.assertEqual(crowded["risk"], "CROWDED")

    def test_volatility_adjusted_risk_and_inverted_sell(self):
        buy = dynamic_risk(100000, "BUY", 1000, 1.0, "US")
        sell = dynamic_risk(100000, "SELL", 1000, 1.0, "US")
        self.assertEqual(buy["status"], "OK")
        self.assertLess(buy["sl"], 100000)
        self.assertGreater(sell["sl"], 100000)
        self.assertGreater(buy["rr_reference"], 1.55)
        self.assertEqual(dynamic_risk(100000, "BUY", 5000, 1, "US")["status"], "WAIT")

    def test_sniper_rejects_wrong_direction(self):
        bars = [Bar(self.start + timedelta(minutes=5*i), 95, 101, 92, 99, 5)
                for i in range(12)]
        self.assertTrue(m5_sniper(bars, "BUY"))
        self.assertFalse(m5_sniper(bars, "SELL"))


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.notifier = Notifier()
        self.created = datetime(2026, 11, 8, 10, 0, 23, tzinfo=UTC)
        self.signal = {
            "side": "BUY", "entry": 100, "sl": 90, "tp1": 120, "tp2": 140,
        }
        self.assertTrue(start_observation(self.store, self.signal, self.created))
        self.first = datetime(2026, 11, 8, 10, 5, tzinfo=UTC)

    def bar(self, start, high, low):
        return Bar(start, 100, high, low, 101, 5)

    def test_tp1_alert_and_later_breakeven_is_only_model(self):
        first = self.bar(self.first, 122, 99)
        self.assertEqual(
            follow_observation(self.store, self.notifier, Provider([first]),
                               datetime(2026, 11, 8, 10, 10, 20, tzinfo=UTC)),
            "observing",
        )
        self.assertTrue(self.store.get("v4_btc_observed_active")["tp1_alerted"])
        self.assertEqual(self.store.get("v4_btc_observed_active")["sl"], 100)
        second = self.bar(self.first + timedelta(minutes=5), 105, 99)
        result = follow_observation(
            self.store, self.notifier, Provider([first, second]),
            datetime(2026, 11, 8, 10, 15, 20, tzinfo=UTC),
        )
        self.assertEqual(result, "stop")
        self.assertEqual(self.store.get("v4_btc_observed_active")["r_multiple"], 0.)
        self.assertIn("نموذج", btc_stats_message(self.store))

    def test_same_bar_stop_and_tp_are_unscored(self):
        first = self.bar(self.first, 130, 88)
        result = follow_observation(
            self.store, self.notifier, Provider([first]),
            datetime(2026, 11, 8, 10, 10, 20, tzinfo=UTC),
        )
        self.assertEqual(result, "ambiguous")
        self.assertIsNone(self.store.get("v4_btc_observed_active")["r_multiple"])
        self.assertIn("غير محسومة", btc_stats_message(self.store))

    def test_gap_is_unverified_not_a_loss(self):
        late = self.bar(self.first + timedelta(minutes=5), 150, 50)
        result = follow_observation(
            self.store, self.notifier, Provider([late]),
            datetime(2026, 11, 8, 10, 15, 20, tzinfo=UTC),
        )
        self.assertEqual(result, "gap")
        self.assertEqual(self.store.get("v4_btc_observed_active")["event"], "DATA_GAP_UNVERIFIED")

    def test_status_and_journal_do_not_identify_actual_account(self):
        self.assertIn("افتراضية", btc_status_message(self.store))
        self.assertIn("ليست أرباح حساب حقيقي", btc_stats_message(self.store))


if __name__ == "__main__":
    unittest.main()
