import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ.setdefault("BRIDGE_URL", "https://example.invalid")
os.environ.setdefault("BRIDGE_PUBLISH_TOKEN", "test-only")

from bridge_emergency_worker import (
    evaluate_emergency,
    evaluate_profit_guardian,
    protected_profit_floor,
    main_morning_window,
    main_profit_lock_sl,
)


class EmergencyEvaluationTests(unittest.TestCase):
    def state(self, side="BUY", price=100.0, profit=0.0):
        return {
            "side": side,
            "price": str(price),
            "open_price": "100.0",
            "sl": "96.0" if side == "BUY" else "104.0",
            "profit": str(profit),
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


class ProfitGuardianTests(unittest.TestCase):
    def state(self, side="BUY", price=102.0, profit=2.0):
        return {
            "side": side,
            "price": str(price),
            "open_price": "100.0",
            "sl": "96.0" if side == "BUY" else "104.0",
            "profit": str(profit),
        }

    def test_guardian_not_armed_below_one_dollar_peak(self):
        reason = evaluate_profit_guardian(
            self.state(price=100.2, profit=0.2),
            [100.8, 100.5, 100.2],
            [0.8, 0.5, 0.2],
            0.8,
        )
        self.assertEqual(reason, (None, False))

    def test_confirmed_profit_correction_requests_soft_close(self):
        reason, hard = evaluate_profit_guardian(
            self.state(price=102.3, profit=2.3),
            [103.0, 102.7, 102.3],
            [3.0, 2.7, 2.3],
            3.0,
        )
        self.assertEqual(reason, "profit_guardian_confirmed_correction")
        self.assertFalse(hard)

    def test_small_pullback_does_not_close(self):
        result = evaluate_profit_guardian(
            self.state(price=102.7, profit=2.7),
            [103.0, 102.8, 102.7],
            [3.0, 2.8, 2.7],
            3.0,
        )
        self.assertEqual(result, (None, False))

    def test_five_dollar_peak_has_three_fifty_hard_floor(self):
        self.assertAlmostEqual(protected_profit_floor(5.0), 3.5)
        reason, hard = evaluate_profit_guardian(
            self.state(price=103.4, profit=3.4),
            [105.0, 104.0, 103.4],
            [5.0, 4.0, 3.4],
            5.0,
        )
        self.assertEqual(reason, "profit_guardian_floor")
        self.assertTrue(hard)

    def test_three_dollar_peak_has_one_eighty_floor(self):
        self.assertAlmostEqual(protected_profit_floor(3.0), 1.8)

    def test_sell_correction_is_mirrored(self):
        reason, hard = evaluate_profit_guardian(
            self.state("SELL", price=97.7, profit=2.3),
            [97.0, 97.3, 97.7],
            [3.0, 2.7, 2.3],
            3.0,
        )
        self.assertEqual(reason, "profit_guardian_confirmed_correction")
        self.assertFalse(hard)


if __name__ == "__main__":
    unittest.main()


class MainMorningPolicyTests(unittest.TestCase):
    def test_palestine_morning_window(self):
        tz = ZoneInfo("Asia/Hebron")
        self.assertTrue(main_morning_window(datetime(2026, 9, 25, 4, 30, tzinfo=tz)))
        self.assertTrue(main_morning_window(datetime(2026, 9, 25, 6, 59, tzinfo=tz)))
        self.assertFalse(main_morning_window(datetime(2026, 9, 25, 7, 0, tzinfo=tz)))

    def test_main_profit_lock_buy_and_sell(self):
        self.assertAlmostEqual(main_profit_lock_sl("BUY", 4200.0, 15.0), 4210.5)
        self.assertAlmostEqual(main_profit_lock_sl("SELL", 4200.0, 15.0), 4189.5)
