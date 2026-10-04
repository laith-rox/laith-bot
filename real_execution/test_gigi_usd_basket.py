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

    def test_gold_usd_relationship_can_detect_classic_inverse(self):
        usd_returns=[0.0007 if i%3==0 else (-0.0005 if i%3==1 else 0.0002) for i in range(75)]
        feeds={}
        for pair,(_,orientation) in gigi_usd_basket.PAIR_SPECS.items():
            feeds[pair]=rows(1.0,[orientation*x for x in usd_returns])
        gold=rows(4000.0,[-1.5*x for x in usd_returns])
        out=gigi_usd_basket.analyze(feeds,gold)
        self.assertEqual(out["gold_relationship"]["state"],"CLASSIC_INVERSE")
        self.assertLess(out["gold_relationship"]["corr_short"],-0.8)

    def test_gold_usd_relationship_can_detect_positive_decoupling(self):
        usd_returns=[0.0006 if i%2==0 else -0.00035 for i in range(75)]
        feeds={}
        for pair,(_,orientation) in gigi_usd_basket.PAIR_SPECS.items():
            feeds[pair]=rows(1.0,[orientation*x for x in usd_returns])
        gold=rows(4000.0,[1.2*x for x in usd_returns])
        out=gigi_usd_basket.analyze(feeds,gold)
        self.assertEqual(out["gold_relationship"]["state"],"DECOUPLED_POSITIVE")
        self.assertGreater(out["gold_relationship"]["corr_short"],0.8)


    def test_inverse_weakening_is_distinct_from_full_decoupling(self):
        usd_returns=[0.0007 if i%3==0 else (-0.0005 if i%3==1 else 0.0002) for i in range(80)]
        feeds={}
        for pair,(_,orientation) in gigi_usd_basket.PAIR_SPECS.items():
            feeds[pair]=rows(1.0,[orientation*x for x in usd_returns])
        gold_returns=[]
        for i,x in enumerate(usd_returns):
            if i < 60:
                gold_returns.append(-1.4*x)
            else:
                gold_returns.append([0.0003,-0.0001,-0.00025,0.00005][i%4])
        gold=rows(4000.0,gold_returns)
        out=gigi_usd_basket.analyze(feeds,gold)
        self.assertEqual(out["gold_relationship"]["state"],"INVERSE_WEAKENING")
        self.assertLess(out["gold_relationship"]["corr_long"],-0.4)
        self.assertGreater(out["gold_relationship"]["corr_short"],out["gold_relationship"]["corr_long"]+0.25)



if __name__=="__main__":
    unittest.main()
