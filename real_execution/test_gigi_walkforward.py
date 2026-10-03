import unittest

import gigi_walkforward


class GigiWalkForwardTests(unittest.TestCase):
    def test_spread_cost_is_r_normalized(self):
        self.assertAlmostEqual(
            gigi_walkforward.spread_cost_r({"spread":20},0.01,2.0),
            0.1,
            places=6,
        )

    def test_cost_never_improves_result(self):
        out=gigi_walkforward.apply_cost({"close_r":1.5},0.2)
        self.assertEqual(out["net_close_r"],1.3)
        loss=gigi_walkforward.apply_cost({"close_r":-1.0},0.2)
        self.assertEqual(loss["net_close_r"],-1.2)

    def test_session_boundary_uses_palestine_clock(self):
        # 2026-10-03 02:00Z resolves to 05:00 Palestine while DST is active.
        self.assertTrue(gigi_walkforward.session_allowed("2026-10-03T02:00:00Z"))
        self.assertFalse(gigi_walkforward.session_allowed("2026-10-03T01:59:00Z"))

    def test_report_has_chronological_holdout(self):
        rows=[]
        for i,r in enumerate([1,1,-1,1,-1,1,-1,1,-1,1]):
            rows.append({
                "time":i,
                "resolved":True,
                "close_r":float(r),
                "net_close_r":float(r)-0.1,
                "outcome":"TARGET" if r>0 else "STOP",
                "mode":"SNIPER",
                "reason":"x",
            })
        out=gigi_walkforward.report(rows)
        self.assertEqual(out["n"],10)
        self.assertGreater(out["train_spread_adjusted"]["n"],0)
        self.assertGreater(out["holdout_spread_adjusted"]["n"],0)

    def test_multi_window_stability_requires_all_windows_adequate(self):
        rows=[
            {"n":50,"mean_r":-0.2},
            {"n":45,"mean_r":-0.1},
            {"n":10,"mean_r":0.8},
        ]
        out=gigi_walkforward.multi_window_stability(rows,min_per_window=20,required_windows=3)
        self.assertEqual(out["status"],"INSUFFICIENT_PER_WINDOW")
        self.assertFalse(out["qualified"])

    def test_multi_window_stable_negative_needs_three_negative_windows(self):
        rows=[
            {"n":50,"mean_r":-0.2},
            {"n":45,"mean_r":-0.1},
            {"n":40,"mean_r":-0.3},
        ]
        out=gigi_walkforward.multi_window_stability(rows,min_per_window=20,required_windows=3)
        self.assertEqual(out["status"],"STABLE_NEGATIVE")
        self.assertTrue(out["qualified"])


    def test_sniper_profit_protection_can_lock_positive_r(self):
        future=[
            {"high":102.5,"low":99.2,"close":102.0},
            {"high":101.5,"low":100.5,"close":100.8},
        ]
        out=gigi_walkforward.protected_outcome(
            "BUY",100.0,2.0,2.0,future,"SNIPER",usd_per_price_unit=1.0
        )
        self.assertTrue(out["resolved"])
        self.assertEqual(out["outcome"],"PROTECTED_STOP")
        self.assertAlmostEqual(out["close_r"],0.5,places=4)
        self.assertTrue(out["protection_activated"])

    def test_main_profit_protection_is_next_bar_conservative(self):
        future=[
            {"high":102.5,"low":99.5,"close":102.0},
            {"high":101.0,"low":100.4,"close":100.6},
        ]
        out=gigi_walkforward.protected_outcome(
            "BUY",100.0,2.0,2.0,future,"MAIN",usd_per_price_unit=1.0
        )
        self.assertTrue(out["resolved"])
        self.assertEqual(out["outcome"],"PROTECTED_STOP")
        self.assertGreater(out["close_r"],0)



if __name__=="__main__":
    unittest.main()
