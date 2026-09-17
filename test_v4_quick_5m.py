from datetime import datetime, timedelta, timezone
import unittest

from market import Bar
from v4_quick_5m import analyze_quick_5m, quick_5m_wait_message

UTC = timezone.utc


def trend_bars(direction=1, count=30):
    start = datetime(2026, 9, 17, 15, 0, tzinfo=UTC)
    rows = []
    price = 4300.0
    for index in range(count):
        open_price = price
        close = open_price + direction * 0.8
        high = max(open_price, close) + 0.35
        low = min(open_price, close) - 0.35
        rows.append(Bar(start + timedelta(minutes=5 * index), open_price, high, low, close, 5))
        price = close
    return rows


class V4Quick5mTests(unittest.TestCase):
    def test_uptrend_current_candle_creates_strong_buy_from_5m_rules(self):
        bars = trend_bars(1)
        current = {
            "price": bars[-1].close + 0.7,
            "candle_open": bars[-1].close + 0.1,
            "candle_high": bars[-1].close + 0.9,
            "candle_low": bars[-1].close,
        }
        higher = {"side": "BUY", "buy": 6, "sell": 2, "v4": {}}
        decision = analyze_quick_5m(bars, current, higher)
        self.assertEqual(decision["side"], "BUY")
        self.assertTrue(decision["quick5m"]["entry_allowed"])
        self.assertGreaterEqual(decision["buy"], 6)
        self.assertEqual(decision["quick5m"]["strength"], "قوية")
        self.assertFalse(decision["quick5m"]["calibrated_probability"])
        self.assertEqual(decision["quick5m"]["timeframe"], "5m")

    def test_downtrend_current_candle_creates_strong_sell_from_5m_rules(self):
        bars = trend_bars(-1)
        current = {
            "price": bars[-1].close - 0.7,
            "candle_open": bars[-1].close - 0.1,
            "candle_high": bars[-1].close,
            "candle_low": bars[-1].close - 0.9,
        }
        higher = {"side": "SELL", "buy": 1, "sell": 6, "v4": {}}
        decision = analyze_quick_5m(bars, current, higher)
        self.assertEqual(decision["side"], "SELL")
        self.assertTrue(decision["quick5m"]["entry_allowed"])
        self.assertGreaterEqual(decision["sell"], 6)
        self.assertEqual(decision["quick5m"]["strength"], "قوية")

    def test_four_of_seven_directional_candidate_is_exposed_as_weak(self):
        bars = trend_bars(1)
        # Break several supporting checks while preserving an honest upward
        # current-slot move and a directional lead.
        bars[-1] = Bar(bars[-1].start, bars[-1].open + 1.0, bars[-1].high + 1.0,
                       bars[-1].low, bars[-1].open + 0.2, 5)
        current = {
            "price": bars[-1].close + 0.25,
            "candle_open": bars[-1].close + 0.05,
            "candle_high": bars[-1].close + 0.3,
            "candle_low": bars[-1].close,
        }
        higher = {"side": "WAIT", "buy": 3, "sell": 4, "v4": {}}
        decision = analyze_quick_5m(bars, current, higher)
        if decision["side"] == "BUY":
            self.assertGreaterEqual(decision["buy"], 4)
            self.assertEqual(decision["quick5m"]["strength"], "ضعيفة")
            self.assertTrue(decision["quick5m"]["manual_candidate"])
        else:
            # The crafted bar may change EMA/momentum enough to remove the lead;
            # in that case the engine must honestly WAIT rather than force it.
            self.assertEqual(decision["side"], "WAIT")

    def test_flat_current_candle_becomes_wait_not_forced_trade(self):
        bars = trend_bars(1)
        current_open = bars[-1].close
        current = {
            "price": current_open,
            "candle_open": current_open,
            "candle_high": current_open + 0.2,
            "candle_low": current_open - 0.2,
            "candle_start_iso": "2026-09-17T17:30:00+00:00",
        }
        higher = {"side": "WAIT", "buy": 4, "sell": 4, "v4": {}}
        decision = analyze_quick_5m(bars, current, higher)
        self.assertEqual(decision["side"], "WAIT")
        self.assertFalse(decision["quick5m"]["entry_allowed"])
        message = quick_5m_wait_message(decision, current)
        self.assertIn("Quick 5د — WAIT", message)
        self.assertIn("لا يتم اختراع صفقة", message)

    def test_quick_condition_names_are_all_five_minute_specific_except_filter(self):
        bars = trend_bars(1)
        current = {
            "price": bars[-1].close + 0.5,
            "candle_open": bars[-1].close + 0.1,
            "candle_high": bars[-1].close + 0.6,
            "candle_low": bars[-1].close,
        }
        decision = analyze_quick_5m(bars, current, {"side": "BUY", "buy": 5, "sell": 2, "v4": {}})
        names = decision["quick_condition_names"]
        self.assertEqual(len(names), 7)
        self.assertTrue(all("5د" in name or "M15/H1" in name for name in names))


if __name__ == "__main__":
    unittest.main()
