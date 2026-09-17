import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from storage import Store
from v4_intelligence import (
    attach_continuation_intelligence,
    classify_trade_lesson,
    enrich_decision,
    quick_hard_blocked,
    record_trade_lesson,
)


UTC = timezone.utc


class Bar:
    def __init__(self, start, close=4000.0):
        self.start = start
        self.end = start + timedelta(minutes=5)
        self.open = close - 0.2
        self.high = close + 0.5
        self.low = close - 0.5
        self.close = close


class V4IntelligenceTests(unittest.TestCase):
    def bars(self, now):
        return [Bar(now - timedelta(minutes=25 - 5 * i)) for i in range(5)]

    def decision(self, **changes):
        base = {
            "side": "BUY",
            "reason": "v4_structural_entry",
            "price": 4000.0,
            "atr": 10.0,
            "rsi": 58.0,
            "buy": 6,
            "sell": 2,
            "checks": {
                "BUY": [True, True, True, True, True, True, True],
                "SELL": [False, False, False, False, False, False, True],
            },
            "context": {"trend": "BUY"},
            "v4": {
                "nearest_support": {"low": 3993.0, "center": 3994.0, "high": 3995.0},
                "nearest_resistance": {"low": 4005.0, "center": 4006.0, "high": 4007.0},
                "breakout_state": "LEVEL_INTACT",
                "volatility_regime": "NORMAL",
                "macro_alignment": "ALIGN",
                "structural_risk": {
                    "valid": True, "stop": 3991.0, "tp1": 4012.6, "tp2": 4019.8,
                    "room_r": 1.5,
                },
                "correction": {
                    "direction": "DOWN", "strength": "WEAK", "triggered": False,
                    "start_zone": {"center": 4008.0}, "target1": 3998.0,
                    "target2": 3994.0, "invalidation": 4010.0,
                },
            },
        }
        for key, value in changes.items():
            base[key] = value
        return base

    def test_compressed_structure_becomes_wait(self):
        now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        enriched = enrich_decision(self.decision(), self.bars(now), now)
        self.assertEqual(enriched["side"], "WAIT")
        self.assertEqual(enriched["reason"], "v4_no_trade_zone")
        intel = enriched["v4"]["intelligence"]
        self.assertTrue(intel["entry_gate"]["hard_block"])
        self.assertIn("compressed_between_support_resistance", intel["entry_gate"]["reasons"])
        self.assertTrue(quick_hard_blocked(enriched))

    def test_open_space_keeps_actionable_side_and_scores_quality(self):
        now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        decision = self.decision()
        decision["v4"]["nearest_resistance"] = {"low": 4030.0, "center": 4031.0, "high": 4032.0}
        decision["v4"]["breakout_state"] = "OPEN_SPACE"
        enriched = enrich_decision(decision, self.bars(now), now)
        self.assertEqual(enriched["side"], "BUY")
        intel = enriched["v4"]["intelligence"]
        self.assertFalse(intel["entry_gate"]["hard_block"])
        self.assertGreaterEqual(intel["confidence"]["score"], 7.0)
        self.assertFalse(intel["confidence"]["calibrated_probability"])
        self.assertIsNotNone(intel["invalidation"]["level"])
        self.assertIsNotNone(intel["wait_plan"]["buy_trigger"])

    def test_failed_break_is_hard_block_for_quick_and_official(self):
        now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        decision = self.decision()
        decision["v4"]["breakout_state"] = "FAILED_BREAK"
        decision["v4"]["nearest_resistance"] = {"low": 4030.0, "center": 4031.0, "high": 4032.0}
        enriched = enrich_decision(decision, self.bars(now), now)
        self.assertEqual(enriched["side"], "WAIT")
        self.assertTrue(quick_hard_blocked(enriched))
        self.assertIn("failed_breakout", enriched["v4"]["intelligence"]["entry_gate"]["reasons"])

    def test_continuation_gets_progress_and_invalidation(self):
        now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        decision = self.decision()
        decision["v4"]["nearest_resistance"] = {"low": 4030.0, "center": 4031.0, "high": 4032.0}
        decision["v4"]["breakout_state"] = "OPEN_SPACE"
        enriched = enrich_decision(decision, self.bars(now), now)
        snap = {"side": "BUY", "price": 4004.5}
        trade = {"side": "BUY", "entry": 4000.0, "initial_sl": 3991.0, "stop": 3991.0}
        result = attach_continuation_intelligence(snap, enriched, trade)
        self.assertEqual(result["progress_r"], 0.5)
        self.assertIsNotNone(result["invalidation"]["level"])
        self.assertIn("components", result["confidence"])

    def test_loss_learning_is_classified_and_idempotent(self):
        trade = {
            "id": "loss-1",
            "side": "BUY",
            "status": "closed",
            "outcome": "STOP",
            "r": -1.0,
            "closed": 12345.0,
            "research_v4": {
                "breakout_state": "FAILED_BREAK",
                "volatility_regime": "HIGH",
                "intelligence": {"confidence": {"score": 4.8}, "data_quality": {"label": "FRESH"}},
            },
        }
        lesson = classify_trade_lesson(trade)
        self.assertEqual(lesson["reason"], "failed_breakout")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "v4.db"))
            try:
                record_trade_lesson(store, trade, "official")
                record_trade_lesson(store, trade, "official")
                journal = store.get("v4_learning_journal")
                self.assertEqual(len(journal), 1)
                self.assertEqual(store.get("v4_learning_summary")["by_reason"]["failed_breakout"], 1)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
