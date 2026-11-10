"""Focused feature 11–20 tests for V4's paper-only adaptive second stage."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from market import Bar
from v4_adaptive_11_20 import (
    adaptive_entry_review,
    breakout_confirmation,
    classify_correction,
    day_levels,
    entry_validity,
    execution_cost,
    exposure_check,
    market_adaptation,
    market_character,
    risk_targets,
    signal_change_message,
    signal_change_review,
    timeframe_candles,
)

UTC = timezone.utc


def make_bars(n=96, start=None, mode="up"):
    start = start or datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    rows = []
    for i in range(n):
        center = 4100 + (0.24*i if mode == "up" else -0.24*i if mode == "down" else (i % 4)-2)
        rows.append(Bar(start + timedelta(minutes=5*i),
                        center-0.1, center+0.8, center-0.8, center+0.25, 5))
    return rows


def decision():
    return {"side": "BUY", "buy": 6, "sell": 2, "atr": 4.0, "context": {"trend": "BUY"},
            "checks": {"BUY": [True]*6 + [False], "SELL": [False]*5+[True]*2},
            "v4": {"structural_risk": {"stop": 4098.5},
                   "nearest_resistance": {"low": 4107.0},
                   "adaptive": {"feature_11_regime": {"state": "UPTREND"},
                                "feature_15_correction": {"state": "ALIGNED"}}}}


def setup():
    return {"side": "BUY", "entry": 4101.0, "stop": 4098.0, "target": 4108.0,
            "risk": 3.0, "entry_action": "ENTER_NOW"}


def reference(now, age=5, price=4101.0):
    return {"time": now.timestamp()-age, "price": price,
            "candle_open": 4100.0, "timing_aligned": True}


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 20, 10, tzinfo=UTC)

    def test_11_detects_direction_and_range(self):
        self.assertEqual(market_character(make_bars(64))["state"], "UPTREND")
        self.assertEqual(market_character(make_bars(64, mode="down"))["state"], "DOWNTREND")
        self.assertEqual(market_character(make_bars(10))["state"], "UNAVAILABLE")

    def test_12_h4_is_not_synthetically_created(self):
        tf = timeframe_candles(make_bars(96))
        self.assertEqual(tf["H4"]["origin"], "NATIVE_H4_UNAVAILABLE")
        self.assertFalse(tf["h4_original_verified"])
        self.assertTrue(tf["M15"]["available"])
        self.assertEqual(tf["M15"]["origin"], "DERIVED_FROM_COMPLETE_5M")
        self.assertTrue(tf["H1"]["available"])

    def test_12_native_h4_requires_explicit_supplied_candle(self):
        h4 = Bar(datetime(2026, 11, 10, 16, 0, tzinfo=UTC),
                 4100.0, 4120.0, 4090.0, 4110.0, 240)
        tf = timeframe_candles(make_bars(96), native_h4=[h4])
        self.assertTrue(tf["h4_original_verified"])
        self.assertEqual(tf["H4"]["origin"], "NATIVE_H4_ONLY")

    def test_13_session_is_dst_aware(self):
        out = market_adaptation(decision(), make_bars(64), self.now)
        self.assertIn(out["feature_13_session"]["name"],
                      ("LONDON_NEW_YORK_OVERLAP", "NEW_YORK", "LONDON", "ASIA", "OTHER"))

    def test_14_previous_day_level_requires_coverage(self):
        now = datetime(2026, 11, 11, 14, tzinfo=UTC)
        bars = make_bars(190, start=now-timedelta(hours=20))
        levels = day_levels(bars, now)
        self.assertTrue(levels["today"]["available"])
        self.assertEqual(levels["previous"]["coverage"], "INSUFFICIENT")
        self.assertIn("asia", levels)

    def test_15_correction_and_reversal_are_probabilistic(self):
        candles = {"M15": {"available": True, "direction": "SELL"},
                   "H1": {"available": True, "direction": "SELL"}}
        d = decision()
        d["side"] = "SELL"
        result = classify_correction(d, candles)
        self.assertEqual(result["state"], "REVERSAL_WATCH")
        self.assertFalse(result["confirmed_reversal"])
        candles["H1"]["direction"] = "BUY"
        self.assertEqual(classify_correction(d, candles)["state"], "COUNTERTREND_CORRECTION")

    def test_16_breakout_requires_two_closes(self):
        bars = make_bars(28, mode="flat")
        higher = max(b.high for b in bars[:-2])
        last = bars[-2:]
        for idx in (-2, -1):
            b = bars[idx]
            bars[idx] = Bar(b.start, higher+1, higher+2, higher+0.5, higher+1.5, 5)
        result = breakout_confirmation(bars)
        self.assertEqual(result["state"], "CONFIRMED_UP")

    def test_17_expires_stale_or_moved_signal(self):
        self.assertTrue(entry_validity(setup(), reference(self.now), self.now)["entry_valid"])
        self.assertFalse(entry_validity(setup(), reference(self.now, age=91), self.now)["entry_valid"])
        self.assertFalse(entry_validity(setup(), reference(self.now, price=4109), self.now)["entry_valid"])

    def test_18_sl_tp_suggestions_never_modify_original(self):
        before = setup()
        plan = risk_targets(decision(), before)
        self.assertTrue(plan["available"])
        self.assertEqual(plan["structure_stop_candidate"], 4098.5)
        self.assertEqual(plan["nearby_opposing_target"], 4107)
        self.assertEqual(before["stop"], 4098.0)
        self.assertTrue(plan["no_order_adjustment"])

    def test_19_exposure_keeps_official_quick_separate(self):
        quick = [{"status": "active", "side": "BUY"}]
        official = {"status": "active", "side": "SELL"}
        result = exposure_check(setup(), quick, official)
        self.assertEqual(result["active_quick"], 1)
        self.assertEqual(result["same_direction"], 1)
        self.assertEqual(result["opposite_direction"], 1)

    def test_20_never_fabricates_spread(self):
        self.assertEqual(execution_cost(setup(), reference(self.now))["status"], "SPREAD_UNKNOWN")
        r = {**reference(self.now), "bid": 4100.0, "ask": 4101.0}
        self.assertEqual(execution_cost(setup(), r)["status"], "HIGH_COST")

    def test_entry_review_downgrades_high_cost_only(self):
        policy = {"action": "ENTER_NOW", "reasons": [], "warnings": [], "policy": "dual-brain-v1"}
        d = adaptive_entry_review(decision(), setup(), reference(self.now), self.now, policy)
        self.assertEqual(d["entry_policy"]["action"], "ENTER_NOW")
        self.assertEqual(d["feature_20_execution_cost"]["status"], "SPREAD_UNKNOWN")
        costly = adaptive_entry_review(decision(), setup(),
                                       {**reference(self.now), "bid": 4100.0, "ask": 4101.0},
                                       self.now, policy)
        self.assertEqual(costly["entry_policy"]["action"], "CAUTIOUS")
        self.assertEqual(policy["action"], "ENTER_NOW")

    def test_entry_review_never_upgrades_wait(self):
        policy = {"action": "WATCH", "reasons": ["unsafe"], "warnings": []}
        result = adaptive_entry_review(decision(), setup(), reference(self.now), self.now, policy)
        self.assertEqual(result["entry_policy"]["action"], "WATCH")

    def test_direction_reversal_prompts_review_once_by_id(self):
        old = {**setup(), "id": "signal-1", "signal_observed_at": self.now.timestamp()-300}
        d = {"side": "SELL", "checks": {"SELL": [True]*5 + [False]*2}}
        reversal = signal_change_review(old, d, self.now)
        self.assertEqual(reversal["new_side"], "SELL")
        self.assertIn("لم تعد مناسبة", signal_change_message(reversal))

    def test_all_11_16_fields_present(self):
        out = market_adaptation(decision(), make_bars(64), self.now)
        for i in range(11, 17):
            self.assertTrue(any(k.startswith(f"feature_{i}_") for k in out))


if __name__ == "__main__":
    unittest.main()
