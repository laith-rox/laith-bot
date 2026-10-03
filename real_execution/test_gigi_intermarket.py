import unittest
from datetime import datetime, timezone, timedelta

import gigi_intermarket


def series(values):
    t0=datetime(2026,10,1,tzinfo=timezone.utc)
    return [{
        "datetime":(t0+timedelta(minutes=15*i)).isoformat(),
        "open":float(v),"high":float(v),"low":float(v),"close":float(v),
        "tick_volume":100,
    } for i,v in enumerate(values)]


class GigiIntermarketTests(unittest.TestCase):
    def test_positive_relation_rise_supports_gold(self):
        gold=series([100+i for i in range(20)])
        oil=series([50+0.5*i for i in range(20)])
        out=gigi_intermarket.analyze(gold,{"WTI":oil})
        self.assertEqual(out["details"]["WTI"]["relation"],"POSITIVE")
        self.assertGreater(out["bull_evidence"],0)

    def test_negative_relation_rise_pressures_gold(self):
        oil_values=[100,101,100,101,100,101,100,101,100,101,
                    100,101,100,101,100,101,100,101,102,103,104]
        gold_values=[100,99,100,99,100,99,100,99,100,99,
                     100,99,100,99,100,99,100,99,98,97,96]
        gold=series(gold_values)
        oil=series(oil_values)
        out=gigi_intermarket.analyze(gold,{"WTI":oil})
        self.assertEqual(out["details"]["WTI"]["relation"],"NEGATIVE")
        self.assertGreater(out["bear_evidence"],0)

    def test_weak_or_missing_data_stays_neutral(self):
        out=gigi_intermarket.analyze(series([100+i for i in range(20)]),{"WTI":[]})
        self.assertEqual(out["bias"],"NEUTRAL")


if __name__=="__main__":
    unittest.main()
