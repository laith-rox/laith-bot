import unittest
from v4_regime_lane_audit import regime_lane_audit


class RegimeLaneAuditTests(unittest.TestCase):
    def test_uptrend_flags_counter_regime_quick(self):
        d = {"side": "BUY", "v4": {"adaptive": {"feature_11_regime": {"state": "UPTREND"}}}}
        result = regime_lane_audit(d, {"side": "SELL"})
        self.assertEqual(result["official"]["alignment"], "ALIGNED")
        self.assertEqual(result["quick"]["alignment"], "COUNTER_REGIME")
        self.assertTrue(result["lanes_disagree"])
        self.assertEqual(d["side"], "BUY")

    def test_downtrend_alignment(self):
        d = {"side": "SELL", "v4": {"adaptive": {"feature_11_regime": {"state": "DOWNTREND"}}}}
        self.assertEqual(regime_lane_audit(d, {"side": "SELL"})["quick"]["alignment"], "ALIGNED")

    def test_range_does_not_invent_trend(self):
        d = {"side": "BUY", "v4": {"adaptive": {"feature_11_regime": {"state": "RANGE"}}}}
        self.assertEqual(regime_lane_audit(d, {"side": "SELL"})["official"]["alignment"], "REGIME_UNCERTAIN")

    def test_wait_and_missing_quick_are_not_conflicts(self):
        result = regime_lane_audit({"side": "WAIT"})
        self.assertEqual(result["official"]["alignment"], "NO_DIRECTION")
        self.assertFalse(result["lanes_disagree"])

    def test_spike_is_uncertain_not_a_direction(self):
        d = {"side": "SELL", "v4": {"adaptive": {"feature_11_regime": {"state": "VOLATILE_SPIKE"}}}}
        self.assertIsNone(regime_lane_audit(d)["regime_direction"])


if __name__ == "__main__":
    unittest.main()
