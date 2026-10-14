import unittest
import gigi_trade_mode


def sig(side="BUY", n=6, h4="UP", confidence=9):
    return {
        "side":side,
        "confidence":confidence,
        "checks":{side:[True]*n+[False]*(7-n)},
        "regime":{"h4_bias":h4,"name":"TREND_UP" if h4=="UP" else "TREND_DOWN"},
        "session":"MAIN",
    }


class GigiTradeModeTests(unittest.TestCase):
    def test_strong_aligned_setup_requests_main(self):
        out=gigi_trade_mode.choose(
            sig(),
            {"alignment":"STRONG_SUPPORT"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"CLEAR"},
        )
        self.assertEqual(out["requested_mode"],"MAIN")
        self.assertFalse(out["authorizes_execution"])

    def test_medium_setup_requests_sniper(self):
        out=gigi_trade_mode.choose(
            sig(n=4,confidence=6),
            {"alignment":"NEUTRAL"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"CLEAR"},
        )
        self.assertEqual(out["requested_mode"],"SNIPER")

    def test_pre_event_blocks_trade_request(self):
        out=gigi_trade_mode.choose(
            sig(),
            {"alignment":"STRONG_SUPPORT"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"HIGH_IMPACT_WINDOW","phase":"PRE_HIGH_EVENT"},
        )
        self.assertEqual(out["requested_mode"],"NO_TRADE")
        self.assertEqual(out["macro_phase"],"PRE_HIGH_EVENT")

    def test_first_high_event_spike_blocks_trade_request(self):
        out=gigi_trade_mode.choose(
            sig(),
            {"alignment":"STRONG_SUPPORT"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"HIGH_IMPACT_WINDOW","phase":"HIGH_EVENT_SHOCK_0_5M"},
        )
        self.assertEqual(out["requested_mode"],"NO_TRADE")

    def test_stable_negative_mode_is_not_recommended_again(self):
        out=gigi_trade_mode.choose(
            sig(n=4,confidence=6),
            {"alignment":"SUPPORT"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"CLEAR","phase":"NORMAL"},
            {"mode_status":"STABLE_NEGATIVE"},
            {"status":"UNQUALIFIED_OR_UNKNOWN"},
            {"state":"RESEARCH_HOLD"},
        )
        self.assertEqual(out["requested_mode"],"NO_TRADE")
        self.assertIn("historical_mode_stable_negative",out["reasons"])

    def test_stable_negative_setup_reason_is_quarantined(self):
        out=gigi_trade_mode.choose(
            sig(),
            {"alignment":"STRONG_SUPPORT"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"CLEAR","phase":"NORMAL"},
            {"mode_status":"PROMISING_UNSTABLE"},
            {"status":"STABLE_NEGATIVE"},
            {"state":"RESEARCH_HOLD"},
        )
        self.assertEqual(out["requested_mode"],"NO_TRADE")
        self.assertIn("historical_setup_reason_stable_negative",out["reasons"])

    def test_promising_unstable_main_remains_shadow_main_candidate(self):
        out=gigi_trade_mode.choose(
            sig(),
            {"alignment":"STRONG_SUPPORT"},
            {"dominant_risk":"BALANCED"},
            {"state":"NORMAL"},
            {"regime":"CLEAR","phase":"NORMAL"},
            {"mode_status":"PROMISING_UNSTABLE"},
            {"status":"STABLE_POSITIVE"},
            {"state":"SHADOW_ONLY"},
        )
        self.assertEqual(out["requested_mode"],"MAIN")
        self.assertIn("main_historical_edge_promising_but_unstable",out["reasons"])

    def test_adverse_crowding_can_demote_main(self):
        out=gigi_trade_mode.choose(
            sig(n=5,confidence=8),
            {"alignment":"SUPPORT"},
            {"dominant_risk":"HIGH_LONG_LIQUIDATION"},
            {"state":"STRESS_EXPANSION"},
            {"regime":"CLEAR"},
        )
        self.assertNotEqual(out["requested_mode"],"MAIN")


if __name__=="__main__":
    unittest.main()
