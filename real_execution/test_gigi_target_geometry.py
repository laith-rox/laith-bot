import unittest

import gigi_target_geometry


def rows(step=1.0,count=30):
    out=[]
    price=100.0
    for i in range(count):
        o=price
        c=price + (step if i%2==0 else -step*0.7)
        out.append({
            "open":o,
            "high":max(o,c)+0.25,
            "low":min(o,c)-0.25,
            "close":c,
        })
        price=c
    return out


class GigiTargetGeometryTests(unittest.TestCase):
    def test_target_distance_is_risk_times_r(self):
        out=gigi_target_geometry.analyze(
            {"reference_close":4000,"risk_distance":5,"target_r":2},
            rows(),
            {"expected_move_1d_pct":1.0},
        )
        self.assertEqual(out["target_distance"],10.0)
        self.assertFalse(out["directional_signal"])

    def test_far_beyond_implied_proxy_is_flagged(self):
        out=gigi_target_geometry.analyze(
            {"reference_close":100,"risk_distance":2,"target_r":2},
            rows(step=0.4),
            {"expected_move_1d_pct":1.0},
        )
        self.assertEqual(out["implied_move_relation"],"FAR_BEYOND_1D_PROXY")
        self.assertIn(out["state"],("AMBITION_HIGH","AMBITION_ELEVATED"))

    def test_short_target_is_descriptive_not_rejected(self):
        atr=gigi_target_geometry._atr(rows())
        out=gigi_target_geometry.analyze(
            {"reference_close":100,"risk_distance":atr*0.2,"target_r":1},
            rows(),
            {},
        )
        self.assertEqual(out["target_atr_bucket"],"SUB_0_75_ATR")
        self.assertEqual(out["state"],"SHORT_HORIZON")
        self.assertFalse(out["execution_gate"])

    def test_missing_inputs_fail_unknown(self):
        out=gigi_target_geometry.analyze({},rows(),{})
        self.assertEqual(out["state"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
