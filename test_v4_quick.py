from datetime import datetime, timedelta, timezone
import unittest

from market import Bar
from v4_quick import advance_quick, build_quick, continuation_snapshot, leading_side, strength_label

UTC = timezone.utc


def decision(buy=5, sell=2, vol="NORMAL", breakout="LEVEL_INTACT"):
    return {
        "side": "WAIT",
        "price": 4300.0,
        "atr": 5.0,
        "rsi": 57.0,
        "buy": buy,
        "sell": sell,
        "checks": {
            "BUY": [True, True, True, True, True, False, False],
            "SELL": [False, False, False, False, False, True, True],
        },
        "v4": {
            "session": "NEW_YORK",
            "volatility_regime": vol,
            "volatility_percentile": 55.0,
            "macro_alignment": "ALIGN",
            "breakout_state": breakout,
            "correction": {"triggered": False, "strength": "WEAK", "direction": "DOWN"},
        },
    }


class V4QuickTests(unittest.TestCase):
    def test_strength_labels(self):
        self.assertEqual(strength_label(4), "ضعيفة")
        self.assertEqual(strength_label(5), "متوسطة")
        self.assertEqual(strength_label(6), "قوية")
        self.assertEqual(strength_label(7), "قوية")

    def test_leading_side_needs_dominance(self):
        self.assertEqual(leading_side(decision(5, 2)), "BUY")
        self.assertIsNone(leading_side(decision(4, 3)))
        self.assertIsNone(leading_side(decision(3, 2)))

    def test_build_quick_has_ratio_rsi_and_rr(self):
        now = datetime(2026, 9, 16, 19, 0, tzinfo=UTC)
        setup = build_quick(decision(), now, quote_price=4301.0)
        self.assertIsNotNone(setup)
        self.assertEqual(setup["side"], "BUY")
        self.assertEqual(setup["score"], 5)
        self.assertEqual(setup["total"], 7)
        self.assertEqual(setup["condition_percent"], 71)
        self.assertEqual(setup["strength"], "متوسطة")
        self.assertEqual(setup["rsi"], 57.0)
        self.assertEqual(setup["rr"], 1.5)
        self.assertEqual(len(setup["conditions"]), 7)
        self.assertAlmostEqual(setup["entry"], 4301.0)
        self.assertAlmostEqual(setup["stop"], 4298.0)
        self.assertAlmostEqual(setup["target"], 4305.5)

    def test_quick_coexists_with_official_candidate_but_blocks_risk_states(self):
        now = datetime(2026, 9, 16, 19, 0, tzinfo=UTC)
        d = decision()
        d["side"] = "BUY"
        self.assertIsNotNone(build_quick(d, now))
        self.assertIsNone(build_quick(decision(vol="EXTREME"), now))
        self.assertIsNone(build_quick(decision(breakout="FAILED_BREAK"), now))

    def test_continuation_snapshot_tracks_original_official_side(self):
        d = decision()
        trade = {
            "side": "BUY", "entry": 4300.0, "stop": 4294.0,
            "tp1": 4308.0, "tp2": 4312.0, "tp1_hit": False,
        }
        snap = continuation_snapshot(d, trade, price=4302.0)
        self.assertEqual(snap["side"], "BUY")
        self.assertEqual(snap["score"], 5)
        self.assertEqual(snap["condition_percent"], 71)
        self.assertEqual(snap["state"], "متوسطة")
        self.assertEqual(snap["price"], 4302.0)

        d["side"] = "SELL"
        snap2 = continuation_snapshot(d, trade, price=4298.0)
        self.assertEqual(snap2["state"], "تحذير")
        self.assertTrue(snap2["opposite_official"])

    def test_target_and_stop_outcomes(self):
        now = datetime(2026, 9, 16, 19, 0, tzinfo=UTC)
        trade = build_quick(decision(), now, quote_price=4300.0)
        target_bar = Bar(now, 4300.0, trade["target"] + 0.1, 4299.5, trade["target"], 5)
        advanced = advance_quick(trade, [target_bar], now + timedelta(minutes=5, seconds=10))
        self.assertEqual(advanced["outcome"], "TARGET")
        self.assertEqual(advanced["r"], 1.5)

        trade2 = build_quick(decision(), now, quote_price=4300.0)
        stop_bar = Bar(now, 4300.0, 4300.2, trade2["stop"] - 0.1, trade2["stop"], 5)
        advanced2 = advance_quick(trade2, [stop_bar], now + timedelta(minutes=5, seconds=10))
        self.assertEqual(advanced2["outcome"], "STOP")
        self.assertEqual(advanced2["r"], -1.0)


if __name__ == "__main__":
    unittest.main()
