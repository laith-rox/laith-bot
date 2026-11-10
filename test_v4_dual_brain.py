"""Deterministic tests for V4 two-brain diagnostics (paper signals only)."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from v4_dual_brain import market_brain, execution_brain, audit_watch_decisions


UTC = timezone.utc


def decision(breakout="OPEN_SPACE", quality="FRESH"):
    return {
        "side": "BUY", "buy": 6, "sell": 2, "atr": 4.0,
        "checks": {"BUY": [True, True, True, True, True, True, False],
                   "SELL": [False, False, True, False, True, False, False]},
        "context": {"trend": "BUY"},
        "v4": {
            "breakout_state": breakout, "volatility_regime": "NORMAL",
            "macro_alignment": "ALIGN",
            "intelligence": {
                "wait_plan": {"buy_trigger": 4102.0, "sell_trigger": 4091.0},
                "data_quality": {"label": quality, "recent_gap": quality == "GAP"},
            },
        },
    }


def quote(now, age=10):
    return {"time": now.timestamp() - age, "timing_aligned": True,
            "candle_open": 4100.0}


def setup():
    return {"side": "BUY", "entry": 4101.0, "stop": 4098.0,
            "target": 4107.0, "cached_market_data": False}


def policy(action):
    return {"action": action, "reasons": ["اتجاه متوافق"],
            "warnings": [], "policy": "flex-v1"}


class Store:
    def __init__(self, data):
        self.data = dict(data)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class DualBrainTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 20, 15, tzinfo=UTC)

    def test_market_brain_preferred_and_alternative(self):
        brain = market_brain(decision(), [], self.now)
        self.assertEqual(brain["market_scenarios"]["preferred"], "BUY")
        self.assertEqual(brain["market_scenarios"]["alternative"], "SELL")
        self.assertEqual(brain["market_scenarios"]["buy_trigger"], 4102.0)

    def test_failed_break_liquidity(self):
        brain = market_brain(decision("FAILED_BREAK"), [], self.now)
        self.assertTrue(brain["liquidity"]["failed_break"])

    def test_wick_liquidity_warning(self):
        bar = SimpleNamespace(open=4099, close=4100, high=4112, low=4098)
        brain = market_brain(decision(), [bar], self.now)
        self.assertTrue(brain["liquidity"]["wick_trap_warning"])

    def test_enter_now_preserved_for_safe_reference(self):
        d = execution_brain(decision(), setup(), quote(self.now),
                            self.now, policy("ENTER_NOW"))
        self.assertEqual(d["execution"]["action"], "ENTER_NOW")
        self.assertEqual(d["execution"]["base_action"], "ENTER_NOW")
        self.assertAlmostEqual(d["execution"]["rr"], 2.0)

    def test_never_upgrades_watch_to_entry(self):
        d = execution_brain(decision(), setup(), quote(self.now),
                            self.now, policy("WATCH"))
        self.assertEqual(d["execution"]["action"], "WATCH")

    def test_stale_reference_downgrades(self):
        d = execution_brain(decision(), setup(), quote(self.now, age=190),
                            self.now, policy("ENTER_NOW"))
        self.assertEqual(d["execution"]["action"], "WATCH")
        self.assertFalse(d["execution"]["data_safe"])

    def test_gap_downgrades(self):
        d = execution_brain(decision(quality="GAP"), setup(), quote(self.now),
                            self.now, policy("ENTER_NOW"))
        self.assertEqual(d["execution"]["action"], "WATCH")

    def test_failed_break_not_enter_now(self):
        d = execution_brain(decision("FAILED_BREAK"), setup(), quote(self.now),
                            self.now, policy("ENTER_NOW"))
        self.assertEqual(d["execution"]["action"], "CAUTIOUS")

    def test_cautious_five_of_seven_not_overridden(self):
        d = decision()
        d["checks"]["BUY"][-2:] = [False, False]
        result = execution_brain(d, setup(), quote(self.now),
                                 self.now, policy("CAUTIOUS"))
        self.assertEqual(result["execution"]["action"], "CAUTIOUS")

    def test_strategy_samples_not_mistaken_for_probabilities(self):
        trades = [{"status": "closed", "r": 1.5, "breakout_state": "OPEN_SPACE"}
                  for _ in range(5)]
        d = execution_brain(decision(), setup(), quote(self.now),
                            self.now, policy("ENTER_NOW"), closed_trades=trades)
        compare = d["strategy_comparison"]
        self.assertTrue(compare["eligible"])
        self.assertEqual(compare["closed_sample_stats"]["TREND"]["sample"], 5)
        self.assertEqual(d["market"]["flexible_rules"]["quality_not_probability"], True)

    def test_learning_is_audit_only(self):
        d = execution_brain(decision(), setup(), quote(self.now),
                            self.now, policy("ENTER_NOW"),
                            learning_summary={"losses": 12})
        self.assertEqual(d["learning"]["audited_losses"], 12)
        self.assertEqual(d["learning"]["mode"], "REVIEW_ONLY_NO_AUTO_TUNING")

    def test_watch_audit_uses_20m_closed_candle(self):
        opened = self.now - timedelta(minutes=25)
        store = Store({"v4_entry_decisions": [
            {"id": "watch-1", "time": opened.isoformat(), "action": "WATCH",
             "side": "BUY", "entry": 4100.0, "stop": 4098.0}
        ]})
        close_time = opened + timedelta(minutes=20)
        bar = SimpleNamespace(end=close_time, close=4102.0)
        count = audit_watch_decisions(store, [bar], self.now)
        self.assertEqual(count, 1)
        self.assertEqual(store.get("v4_watch_audit")[0]["hypothetical_20m_r"], 1)
        self.assertEqual(audit_watch_decisions(store, [bar], self.now), 0)


if __name__ == "__main__":
    unittest.main()
