import unittest
from datetime import datetime, timezone, timedelta
import math

import gigi_usd_basket


def rows(start, returns, quote="direct"):
    t0=datetime(2026,10,1,tzinfo=timezone.utc)
    value=float(start)
    out=[]
    for i,r in enumerate(returns):
        value *= math.exp(float(r))
        out.append({
            "datetime":(t0+timedelta(minutes=15*i)).isoformat(),
            "open":value,"high":value,"low":value,"close":value,
        })
    return out


class GigiUSDBasketTests(unittest.TestCase):
    def test_strong_usd_impulse_requires_breadth(self):
        calm=[0.00002*(-1 if i%2 else 1) for i in range(70)]
        feeds={}
        for pair,(_,orientation) in gigi_usd_basket.PAIR_SPECS.items():
            shock=(0.004 if orientation>0 else -0.004)
            feeds[pair]=rows(1.0, calm+[shock]*5)
        out=gigi_usd_basket.analyze(feeds)
        self.assertEqual(out["state"],"USD_STRONG_IMPULSE")
        self.assertGreaterEqual(out["coverage"],0.99)
        self.assertGreater(out["breadth"],0.9)
        self.assertFalse(out["official_dxy"])

    def test_weak_usd_impulse_detected(self):
        calm=[0.00002*(-1 if i%2 else 1) for i in range(70)]
        feeds={}
        for pair,(_,orientation) in gigi_usd_basket.PAIR_SPECS.items():
            shock=(-0.004 if orientation>0 else 0.004)
            feeds[pair]=rows(1.0, calm+[shock]*5)
        out=gigi_usd_basket.analyze(feeds)
        self.assertEqual(out["state"],"USD_WEAK_IMPULSE")

    def test_low_pair_coverage_fails_neutral(self):
        calm=[0.0001 for _ in range(80)]
        out=gigi_usd_basket.analyze({"USDCHF":rows(1.0,calm)})
        self.assertEqual(out["state"],"INSUFFICIENT_COVERAGE")
        self.assertFalse(out["directional_signal"])

    def test_synthetic_is_explicitly_not_official_dxy(self):
        out=gigi_usd_basket.analyze({})
        self.assertFalse(out["official_dxy"])
        self.assertEqual(out["source"],"BROKER_NATIVE_DXY_STYLE_SYNTHETIC")


if __name__=="__main__":
    unittest.main()
