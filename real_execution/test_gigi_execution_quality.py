import unittest

import gigi_execution_quality


def rows(step=1.0,count=30):
    out=[]
    price=100.0
    for i in range(count):
        o=price
        c=price+(step if i%2==0 else -step*0.7)
        out.append({
            "open":o,"high":max(o,c)+0.25,"low":min(o,c)-0.25,"close":c
        })
        price=c
    return out


class GigiExecutionQualityTests(unittest.TestCase):
    def test_normal_spread_is_non_directional(self):
        atr=gigi_execution_quality._atr(rows())
        out=gigi_execution_quality.analyze(
            {"spread_usd":atr*0.02,"tick_age_seconds":1,"terminal_trade_allowed":True},
            rows(),{"state":"NORMAL"}
        )
        self.assertEqual(out["quality"],"NORMAL")
        self.assertFalse(out["directional_signal"])

    def test_wide_spread_is_detected(self):
        atr=gigi_execution_quality._atr(rows())
        out=gigi_execution_quality.analyze(
            {"spread_usd":atr*0.10,"tick_age_seconds":1,"terminal_trade_allowed":True},
            rows(),{"state":"NORMAL"}
        )
        self.assertEqual(out["quality"],"WIDE")

    def test_extreme_spread_is_detected(self):
        atr=gigi_execution_quality._atr(rows())
        out=gigi_execution_quality.analyze(
            {"spread_usd":atr*0.20,"tick_age_seconds":1,"terminal_trade_allowed":True},
            rows(),{"state":"NORMAL"}
        )
        self.assertEqual(out["quality"],"EXTREME")

    def test_autotrading_off_is_explicit(self):
        out=gigi_execution_quality.analyze(
            {"spread_usd":0.1,"tick_age_seconds":1,"terminal_trade_allowed":False},
            rows(),{"state":"NORMAL"}
        )
        self.assertEqual(out["quality"],"BLOCKED_TERMINAL")

    def test_stale_tick_precedes_spread_label(self):
        out=gigi_execution_quality.analyze(
            {"spread_usd":0.01,"tick_age_seconds":15,"terminal_trade_allowed":True},
            rows(),{"state":"NORMAL"}
        )
        self.assertEqual(out["quality"],"STALE_TICK")


if __name__=="__main__":
    unittest.main()
