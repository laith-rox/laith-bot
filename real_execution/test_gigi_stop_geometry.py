import unittest

import gigi_stop_geometry


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


class GigiStopGeometryTests(unittest.TestCase):
    def test_small_stop_is_recorded_as_inside_noise_bucket(self):
        m15=rows(step=1.0)
        out=gigi_stop_geometry.analyze({"risk_distance":0.20,"mode":"SNIPER"},m15,{"state":"NORMAL"})
        self.assertEqual(out["state"],"SUB_0_35_ATR")
        self.assertEqual(out["noise_exposure"],"HIGH")
        self.assertFalse(out["directional_signal"])

    def test_expansion_makes_sub_atr_geometry_high_noise(self):
        m15=rows(step=1.0)
        atr=gigi_stop_geometry._atr(m15)
        out=gigi_stop_geometry.analyze(
            {"risk_distance":atr*0.60,"mode":"MAIN"},m15,{"state":"REALIZED_EXPANSION"}
        )
        self.assertEqual(out["state"],"0_35_TO_0_75_ATR")
        self.assertEqual(out["noise_exposure"],"HIGH")

    def test_wider_geometry_is_only_descriptive(self):
        m15=rows(step=1.0)
        atr=gigi_stop_geometry._atr(m15)
        out=gigi_stop_geometry.analyze({"risk_distance":atr*1.5,"mode":"MAIN"},m15)
        self.assertEqual(out["state"],"1_25_TO_2_ATR")
        self.assertEqual(out["noise_exposure"],"LOW")
        self.assertEqual(out["note"],"shadow_geometry_not_stop_instruction")

    def test_missing_risk_is_unknown(self):
        out=gigi_stop_geometry.analyze({"risk_distance":0},rows())
        self.assertEqual(out["state"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
