import unittest

import gigi_setup


class GigiSetupTests(unittest.TestCase):
    def test_trend_continuation_is_distinct(self):
        out=gigi_setup.classify(
            {"side":"BUY"},
            {"name":"TREND_UP","h4_bias":"UP"},
            {},
            {},
            {},
            {},
            {"vwap_relation":"ABOVE_ACCEPTANCE","range_event":"NONE"},
            {},
            {},
        )
        self.assertEqual(out["primary"],"TREND_CONTINUATION")
        self.assertFalse(out["directional_signal"])

    def test_liquidity_reversal_detected(self):
        out=gigi_setup.classify(
            {"side":"BUY"},
            {"name":"RANGE","h4_bias":"NEUTRAL"},
            {"event":"SELL_SIDE_SWEEP"},
            {},
            {},
            {},
            {"vwap_relation":"CROSSING","range_event":"FAILED_BREAK_BELOW"},
            {},
            {},
        )
        self.assertEqual(out["primary"],"LIQUIDITY_REVERSAL")
        self.assertGreaterEqual(out["primary_score"],5)

    def test_event_digestion_detected_after_shock(self):
        out=gigi_setup.classify(
            {"side":"SELL"},
            {"name":"TRANSITION","h4_bias":"NEUTRAL"},
            {},
            {"phase":"HIGH_EVENT_DIGESTION_5_15M"},
            {"state":"SHOCK_REVERSED"},
            {},
            {},
            {},
            {},
        )
        self.assertEqual(out["primary"],"EVENT_DIGESTION")

    def test_squeeze_liquidation_detected(self):
        out=gigi_setup.classify(
            {"side":"SELL"},
            {"name":"TREND_DOWN","h4_bias":"DOWN"},
            {},
            {},
            {},
            {"dominant_risk":"HIGH_LONG_LIQUIDATION"},
            {},
            {},
            {},
        )
        self.assertEqual(out["primary"],"SQUEEZE_LIQUIDATION")

    def test_unclear_market_stays_unclear(self):
        out=gigi_setup.classify({"side":"BUY"})
        self.assertEqual(out["primary"],"NO_CLEAR_ARCHETYPE")


if __name__=="__main__":
    unittest.main()
