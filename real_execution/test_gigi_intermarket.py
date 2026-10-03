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

    def test_wti_and_brent_do_not_double_count_same_family(self):
        gold=series([100+i for i in range(20)])
        wti=series([50+0.5*i for i in range(20)])
        brent=series([60+0.6*i for i in range(20)])
        out=gigi_intermarket.analyze(gold,{"WTI":wti,"BRENT":brent})
        self.assertEqual(out["family_details"]["ENERGY"]["members"],2)
        self.assertLessEqual(out["bull_evidence"],1.0)
        self.assertEqual(out["method"],"dual_window_correlation_family_deduplicated")

    def test_related_family_conflict_averages_instead_of_stacking(self):
        gold=series([100+i for i in range(20)])
        up=series([50+0.5*i for i in range(20)])
        down=series([80-0.5*i for i in range(20)])
        out=gigi_intermarket.analyze(gold,{"WTI":up,"BRENT":down})
        self.assertEqual(out["family_details"]["ENERGY"]["members"],2)
        self.assertLess(abs(out["family_details"]["ENERGY"]["vote"]),0.25)


    def test_flipping_relationship_does_not_vote(self):
        gold=[100.0]
        other=[50.0]
        # 64 returns: first 40 move together, last 24 move opposite.
        for i in range(64):
            r=0.01 if i%2==0 else -0.008
            gold.append(gold[-1]*(1+r))
            other_r=r if i<40 else -r
            other.append(other[-1]*(1+other_r))
        out=gigi_intermarket.analyze(series(gold),{"WTI":series(other)})
        detail=out["details"]["WTI"]
        self.assertEqual(detail["relationship_stability"],"FLIPPING")
        self.assertEqual(detail["signed_contribution"],0.0)
        self.assertEqual(out["bias"],"NEUTRAL")
        self.assertEqual(out["relationship_state"],"FLIPPING_PRESENT")



if __name__=="__main__":
    unittest.main()
