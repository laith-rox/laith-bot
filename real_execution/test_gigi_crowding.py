import unittest

import gigi_crowding


class GigiCrowdingTests(unittest.TestCase):
    def test_long_liquidation_risk_needs_context_and_speed(self):
        out = gigi_crowding.analyze(
            {"regime":"LONG_BIASED_DELEVERAGING","crowding":"ELEVATED_LONG"},
            {"state":"STRESS_EXPANSION"},
            {"event":"BUY_SIDE_SWEEP","pressure":"BEARISH"},
            {"regime":"BROAD_OUTFLOW"},
            {"h4_bias":"DOWN"},
        )
        self.assertEqual(out["long_state"], "HIGH_LONG_LIQUIDATION")
        self.assertTrue(out["speed_gate"])
        self.assertGreater(out["long_liquidation_score"], out["short_squeeze_score"])

    def test_short_squeeze_risk_detected(self):
        out = gigi_crowding.analyze(
            {"regime":"SHORT_BIASED_COVERING","crowding":"ELEVATED_SHORT"},
            {"state":"REALIZED_EXPANSION"},
            {"event":"SELL_SIDE_SWEEP","pressure":"BULLISH"},
            {"regime":"BROAD_INFLOW"},
            {"h4_bias":"UP"},
        )
        self.assertEqual(out["short_state"], "HIGH_SHORT_SQUEEZE")
        self.assertGreater(out["short_squeeze_score"], out["long_liquidation_score"])

    def test_without_speed_gate_high_score_is_watch_not_high(self):
        out = gigi_crowding.analyze(
            {"regime":"LONG_BIASED_DELEVERAGING","crowding":"ELEVATED_LONG"},
            {"state":"NORMAL"},
            {"event":"BUY_SIDE_SWEEP","pressure":"BEARISH"},
            {"regime":"BROAD_OUTFLOW"},
            {"h4_bias":"DOWN"},
        )
        self.assertEqual(out["long_state"], "WATCH_LONG_LIQUIDATION")
        self.assertFalse(out["speed_gate"])

    def test_crowding_is_not_direction_signal(self):
        out = gigi_crowding.analyze()
        self.assertFalse(out["directional_signal"])
        self.assertEqual(out["note"], "crowding_risk_context_not_entry_signal")


if __name__=="__main__":
    unittest.main()
