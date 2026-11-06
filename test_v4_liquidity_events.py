import unittest
from v4_liquidity_events import detect_liquidity_event

class LiquidityTests(unittest.TestCase):
    def setUp(self):
        self.base = [{"open": 100, "high": 102, "low": 98, "close": 100} for _ in range(12)]

    def test_buy_side_sweep_rejection(self):
        result = detect_liquidity_event(self.base + [{"open": 100, "high": 104, "low": 99, "close": 101}])
        self.assertEqual(result["event"], "BUY_SIDE_SWEEP_REJECTION")
        self.assertFalse(result["retest_confirmed"])

    def test_sell_side_sweep_rejection(self):
        result = detect_liquidity_event(self.base + [{"open": 100, "high": 101, "low": 96, "close": 99}])
        self.assertEqual(result["event"], "SELL_SIDE_SWEEP_REJECTION")

    def test_breakout_not_automatically_confirmed(self):
        result = detect_liquidity_event(self.base + [{"open": 100, "high": 105, "low": 99, "close": 104}])
        self.assertEqual(result["event"], "BREAKOUT_ABOVE_RANGE")
        self.assertFalse(result["retest_confirmed"])

    def test_invalid_input(self):
        self.assertEqual(detect_liquidity_event([])["event"], "UNKNOWN")
        self.assertEqual(detect_liquidity_event(self.base + [{"open": 100, "high": 99, "low": 101, "close": 100}])["event"], "UNKNOWN")

if __name__ == '__main__':
    unittest.main()
