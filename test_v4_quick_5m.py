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
    def test_uptrend_current_candle_creates_buy_from_5m_rules(self):
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
        self.assertGreaterEqual(decision["buy"], 5)
        self.assertGreaterEqual(decision["buy"] - decision["sell"], 2)
        self.assertEqual(decision["quick5m"]["timeframe"], "5m")
        self.assertNotEqual(decision["atr"], higher.get("atr"))

    def test_downtrend_current_candle_creates_sell_from_5m_rules(self):
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
        self.assertGreaterEqual(decision["sell"], 5)
        self.assertGreaterEqual(decision["sell"] - decision["buy"], 2)

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
        self.assertIn("لا يتم إجبار صفقة", message)

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
