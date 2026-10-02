from datetime import datetime, timedelta, timezone
import unittest

from gigi_gold_brain import GigiGoldBrain
from live_api import _yahoo_payload_to_bars
from market import Bar

UTC = timezone.utc


def b(dt, o, h, l, c):
    return Bar(dt, o, h, l, c)


class GigiGoldBrainStoryTests(unittest.TestCase):
    def test_new_york_rollover_defines_gold_day(self):
        before = datetime(2026, 10, 2, 20, 55, tzinfo=UTC)  # 16:55 NY
        after = datetime(2026, 10, 2, 21, 5, tzinfo=UTC)    # 17:05 NY
        self.assertNotEqual(
            GigiGoldBrain._trading_day(before),
            GigiGoldBrain._trading_day(after),
        )

    def test_bullish_engulfing_is_detected(self):
        start = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
        bars = [
            b(start, 100, 101, 97, 98),
            b(start + timedelta(minutes=5), 97.5, 102, 97, 101.5),
        ]
        story = GigiGoldBrain._candle_story(bars)
        self.assertEqual(story["lastPattern"], "BULL_ENGULFING")

    def test_liquidity_map_finds_nearest_levels(self):
        daily = {
            "available": True,
            "previous": {"high": 110, "low": 90, "open": 100, "close": 105},
            "today": {"high": 106, "low": 96, "open": 101, "close": 103},
        }
        weekly = {
            "available": True,
            "previous": {"high": 120, "low": 80, "open": 95, "close": 108},
        }
        sessions = {"ranges": {"ASIA": {"high": 104, "low": 98, "open": 100, "close": 102}}}
        liquidity = GigiGoldBrain._liquidity_map(103, daily, weekly, sessions)
        self.assertEqual(liquidity["nearestAbove"]["price"], 104)
        self.assertEqual(liquidity["nearestBelow"]["price"], 101)

    def test_regime_detects_directional_trend(self):
        start = datetime(2026, 9, 30, 0, 0, tzinfo=UTC)
        m15 = []
        h1 = []
        for i in range(40):
            m15.append(Bar(start + timedelta(minutes=15*i), 100+i, 101+i, 99+i, 100.8+i, 15))
            h1.append(Bar(start + timedelta(hours=i), 100+2*i, 102+2*i, 99+2*i, 101.5+2*i, 60))
        regime = GigiGoldBrain._market_regime(m15, h1)
        self.assertEqual(regime["type"], "TREND")
        self.assertEqual(regime["direction"], "UP")

    def test_confidence_is_alignment_score_not_probability(self):
        analysis = {
            "conditions": {"passed": 6},
            "storyAlignment": "SUPPORTS",
            "marketRegime": {"type": "TREND", "direction": "UP"},
            "bias": "BUY",
        }
        score = GigiGoldBrain._decision_score(
            analysis, {"status": "SUPPORTS"}, {"blackout": False}
        )
        self.assertGreaterEqual(score, 80)
        capped = GigiGoldBrain._decision_score(
            analysis, {"status": "SUPPORTS"}, {"blackout": True}
        )
        self.assertLessEqual(capped, 40)

    def test_scenario_includes_liquidity_and_invalidation(self):
        analysis = {
            "bias": "BUY",
            "dailyStory": {"event": "INSIDE_PREVIOUS_RANGE"},
            "liquidityMap": {
                "nearestAbove": {"price": 110, "labels": ["PDH"]},
                "nearestBelow": {"price": 100, "labels": ["TODAY_OPEN"]},
            },
            "invalidation": 98,
        }
        scenario = GigiGoldBrain._scenario(analysis, "ENTER")
        self.assertEqual(scenario["primary"], "BUY_CONTINUATION")
        self.assertEqual(scenario["invalidation"], 98)
        self.assertEqual(scenario["nextLiquidityAbove"]["price"], 110)

    def test_previous_high_sweep_and_rejection(self):
        start = datetime(2026, 10, 1, 21, 0, tzinfo=UTC)
        bars = []
        # Prior trading day: 100-110.
        for i in range(12):
            bars.append(b(start + timedelta(minutes=5*i), 104, 110, 100, 105))
        # Current trading day trades above 110, then closes back below.
        current = start + timedelta(days=1)
        bars += [
            b(current, 105, 111.5, 104, 109),
            b(current + timedelta(minutes=5), 109, 110, 106, 108),
        ]
        story = GigiGoldBrain._daily_story(
            bars, current + timedelta(minutes=15)
        )
        self.assertTrue(story["sweptPreviousHigh"])
        self.assertEqual(story["event"], "HIGH_SWEEP_REJECTION")
        self.assertEqual(story["directionalHint"], "SELL")
    def test_fallback_bars_are_basis_adjusted_to_live_spot(self):
        start = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
        count = 1205
        stamps = [int((start + timedelta(minutes=5*i)).timestamp()) for i in range(count)]
        closes = [1000 + i * 0.1 for i in range(count)]
        payload = {
            "chart": {"result": [{
                "timestamp": stamps,
                "indicators": {"quote": [{
                    "open": [v-0.05 for v in closes],
                    "high": [v+0.25 for v in closes],
                    "low": [v-0.25 for v in closes],
                    "close": closes,
                }]},
            }]}
        }
        now = start + timedelta(minutes=5*count + 1)
        bars = _yahoo_payload_to_bars(payload, 2100.0, now)
        self.assertGreaterEqual(len(bars), 1200)
        self.assertAlmostEqual(bars[-1].close, 2100.0, places=6)
        self.assertGreater(bars[-1].high, bars[-1].close)
        self.assertLess(bars[-1].low, bars[-1].close)


if __name__ == "__main__":
    unittest.main()
