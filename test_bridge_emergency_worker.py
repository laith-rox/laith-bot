import os
import unittest

os.environ.setdefault("BRIDGE_URL", "https://example.invalid")
os.environ.setdefault("BRIDGE_PUBLISH_TOKEN", "test-only")

from bridge_emergency_worker import evaluate_emergency


class EmergencyEvaluationTests(unittest.TestCase):
    def state(self, side="BUY", price=100.0):
        return {
            "side": side,
            "price": str(price),
            "open_price": "100.0",
            "sl": "96.0" if side == "BUY" else "104.0",
        }

    def test_failed_breakout_buy_closes_before_stop(self):
        samples = [100.0, 100.5, 101.0, 100.7, 100.1, 99.6, 99.0]
        reason, hard = evaluate_emergency(self.state(price=99.0), samples)
        self.assertEqual(reason, "emergency_failed_breakout")
        self.assertFalse(hard)

    def test_failed_breakout_sell_is_mirrored(self):
        samples = [100.0, 99.5, 99.0, 99.3, 99.9, 100.4, 101.0]
        reason, hard = evaluate_emergency(self.state("SELL", 101.0), samples)
        self.assertEqual(reason, "emergency_failed_breakout")
        self.assertFalse(hard)

    def test_normal_pullback_that_holds_profit_does_not_close(self):
        samples = [100.0, 100.5, 101.0, 101.2, 100.9, 100.8, 100.9]
        self.assertEqual(evaluate_emergency(self.state(price=100.9), samples), (None, False))

    def test_near_stop_is_immediate(self):
        samples = [100.0, 99.5, 98.8, 97.8, 97.0, 96.5]
        reason, hard = evaluate_emergency(self.state(price=96.5), samples)
        self.assertEqual(reason, "emergency_near_stop")
        self.assertTrue(hard)


if __name__ == "__main__":
    unittest.main()
