import os
import unittest
from unittest.mock import patch

os.environ.setdefault("BRIDGE_URL", "https://example.invalid")
os.environ.setdefault("BRIDGE_PUBLISH_TOKEN", "test-only")

from bridge_emergency_worker import (
    evaluate_emergency,
    evaluate_profit_guardian,
    protected_profit_floor,
    select_exit_reason,
    manage_close,
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

    def test_early_normal_pullback_does_not_trigger_accelerating_loss(self):
        # Mirrors the failure mode seen on the morning MAIN: about one-third
        # of planned stop risk against entry, followed by recovery potential.
        samples = [100.0, 99.9, 99.7, 99.4, 99.1, 98.9, 98.8]
        reason, hard = evaluate_emergency(self.state(price=98.8), samples)
        self.assertNotEqual(reason, "emergency_accelerating_loss")
        self.assertFalse(hard)

    def test_deep_sustained_loss_still_triggers_accelerating_loss(self):
        samples = [100.0, 99.8, 99.6, 99.3, 99.0, 98.7, 98.4, 98.1, 97.8, 97.5]
        reason, hard = evaluate_emergency(self.state(price=97.5), samples)
        self.assertEqual(reason, "emergency_accelerating_loss")
        self.assertFalse(hard)


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


class RuntimePolicyTests(unittest.TestCase):
    def test_soft_loss_reversal_is_diagnostic_only(self):
        self.assertEqual(
            select_exit_reason("emergency_confirmed_reversal", False, None, False),
            (None, False),
        )

    def test_near_stop_still_closes_immediately(self):
        self.assertEqual(
            select_exit_reason("emergency_near_stop", True, None, False),
            ("emergency_near_stop", True),
        )

    def test_profit_guardian_still_controls_profitable_trade(self):
        self.assertEqual(
            select_exit_reason(
                "emergency_failed_breakout", False,
                "profit_guardian_confirmed_correction", False,
            ),
            ("profit_guardian_confirmed_correction", False),
        )


if __name__ == "__main__":
    unittest.main()
