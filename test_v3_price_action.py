from datetime import datetime, timedelta, timezone
import unittest

from market import Bar
from v3_price_action import confirmed_pivots, breakout_state, structural_risk_plan
from v3_research import research_gate

UTC = timezone.utc


def bars15(specs):
    start = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    return [Bar(start + timedelta(minutes=15 * i), o, h, l, c, 15)
            for i, (o, h, l, c) in enumerate(specs)]


def expand_to_5m(specs):
    start = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    out = []
    for i, (o, h, l, c) in enumerate(specs):
        bucket = start + timedelta(minutes=15 * i)
        # Three complete aligned bars. Aggregate open/high/low/close reproduces spec.
        out.append(Bar(bucket, o, h, l, (o + c) / 2, 5))
        out.append(Bar(bucket + timedelta(minutes=5), (o + c) / 2, h, l, (o + c) / 2, 5))
        out.append(Bar(bucket + timedelta(minutes=10), (o + c) / 2, h, l, c, 5))
    return out


class PivotTests(unittest.TestCase):
    def test_pivot_requires_right_hand_confirmation(self):
        specs = [
            (1, 2, 0.5, 1.5),
            (1.5, 3, 1, 2.5),
            (2.5, 6, 2, 4),
            (4, 3.5, 1.5, 2.5),
            (2.5, 3, 1, 2),
        ]
        pivots = confirmed_pivots(bars15(specs), left=2, right=2)
        self.assertTrue(any(p["kind"] == "HIGH" and p["index"] == 2 for p in pivots))
        # Without both right-side bars the same apparent high is not yet confirmed.
        self.assertFalse(confirmed_pivots(bars15(specs[:4]), left=2, right=2))


class BreakoutTests(unittest.TestCase):
    def test_wick_through_resistance_close_back_inside_is_failed_break(self):
        specs = [
            (98.5, 99.2, 98.0, 99.0),
            (99.0, 99.4, 98.6, 99.2),
            (99.2, 99.7, 98.9, 99.5),
            (99.5, 100.1, 99.2, 99.8),
            (99.8, 100.7, 99.4, 99.9),
        ]
        level = {"low": 99.8, "center": 100.0, "high": 100.2}
        levels = {"atr": 2.0, "nearest_resistance": level, "nearest_support": None}
        state = breakout_state(expand_to_5m(specs), "BUY", levels)
        self.assertEqual(state["state"], "FAILED_BREAK")


class StructuralRiskTests(unittest.TestCase):
    def base(self):
        return {"side": "BUY", "price": 100.0, "atr": 2.0}

    def test_stop_is_beyond_support_and_reward_room_is_checked(self):
        support = {"low": 98.0, "center": 98.2, "high": 98.4}
        resistance = {"low": 103.8, "center": 104.0, "high": 104.2}
        plan = structural_risk_plan(
            self.base(),
            {"atr": 2.0, "supports": [support], "resistances": [resistance],
             "nearest_support": support, "nearest_resistance": resistance},
            {"state": "LEVEL_INTACT"},
        )
        self.assertTrue(plan["valid"])
        self.assertLess(plan["stop"], support["low"])
        self.assertGreaterEqual(plan["room_r"], 1.15)
        self.assertGreater(plan["tp1"], 100.0)

    def test_trade_is_vetoed_if_resistance_leaves_too_little_room(self):
        support = {"low": 98.0, "center": 98.2, "high": 98.4}
        resistance = {"low": 100.8, "center": 101.0, "high": 101.2}
        plan = structural_risk_plan(
            self.base(),
            {"atr": 2.0, "supports": [support], "resistances": [resistance],
             "nearest_support": support, "nearest_resistance": resistance},
            {"state": "LEVEL_INTACT"},
        )
        self.assertFalse(plan["valid"])
        self.assertEqual(plan["reason"], "opposing_structure_too_close")


class GatePriceActionTests(unittest.TestCase):
    def base(self, side="BUY"):
        return {"side": side, "forced": False, "reason": "entry_conditions_met"}

    def test_failed_break_blocks_entry(self):
        pa = {"available": True, "breakout": {"state": "FAILED_BREAK"},
              "correction": {}, "risk_plan": {"valid": True}}
        self.assertEqual(
            research_gate(self.base(), "LONDON", {"label": "NORMAL"}, None, pa),
            "v3_failed_breakout_against_entry",
        )

    def test_strong_down_correction_blocks_buy(self):
        pa = {"available": True, "breakout": {"state": "LEVEL_INTACT"},
              "correction": {"triggered": True, "strength": "STRONG", "direction": "DOWN"},
              "risk_plan": {"valid": True}}
        self.assertEqual(
            research_gate(self.base("BUY"), "LONDON", {"label": "NORMAL"}, None, pa),
            "v3_strong_correction_against_entry",
        )

    def test_strong_up_correction_does_not_block_buy(self):
        pa = {"available": True, "breakout": {"state": "LEVEL_INTACT"},
              "correction": {"triggered": True, "strength": "STRONG", "direction": "UP"},
              "risk_plan": {"valid": True}}
        self.assertIsNone(
            research_gate(self.base("BUY"), "LONDON", {"label": "NORMAL"}, None, pa)
        )

    def test_strong_up_correction_blocks_sell(self):
        pa = {"available": True, "breakout": {"state": "LEVEL_INTACT"},
              "correction": {"triggered": True, "strength": "STRONG", "direction": "UP"},
              "risk_plan": {"valid": True}}
        self.assertEqual(
            research_gate(self.base("SELL"), "LONDON", {"label": "NORMAL"}, None, pa),
            "v3_strong_correction_against_entry",
        )


if __name__ == "__main__":
    unittest.main()
