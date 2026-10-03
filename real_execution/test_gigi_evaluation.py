import unittest

import gigi_evaluation


def bars(high, low, close, n):
    return [{"high":high,"low":low,"close":close} for _ in range(n)]


class GigiEvaluationTests(unittest.TestCase):
    def test_sniper_and_main_use_different_horizons(self):
        self.assertEqual(gigi_evaluation.horizon_bars("SNIPER"),12)
        self.assertEqual(gigi_evaluation.horizon_bars("MAIN"),36)

    def test_target_resolves_before_full_horizon(self):
        rows=[{"high":102.5,"low":99.5,"close":102.0}]
        out=gigi_evaluation.evaluate("BUY",100,1,2,rows,"MAIN")
        self.assertTrue(out["resolved"])
        self.assertEqual(out["outcome"],"TARGET")
        self.assertEqual(out["horizon_bars"],36)

    def test_no_touch_remains_pending_until_horizon(self):
        out=gigi_evaluation.evaluate(
            "BUY",100,1,2,bars(100.4,99.6,100.1,10),"SNIPER"
        )
        self.assertFalse(out["resolved"])
        self.assertEqual(out["outcome"],"PENDING")

    def test_horizon_close_resolves_after_full_window(self):
        out=gigi_evaluation.evaluate(
            "BUY",100,1,3,bars(100.5,99.5,100.25,12),"SNIPER"
        )
        self.assertTrue(out["resolved"])
        self.assertEqual(out["outcome"],"HORIZON")
        self.assertAlmostEqual(out["close_r"],0.25,places=4)

    def test_same_bar_stop_and_target_is_conservative_stop(self):
        rows=[{"high":102.2,"low":98.8,"close":101.0}]
        out=gigi_evaluation.evaluate("BUY",100,1,2,rows,"SNIPER")
        self.assertEqual(out["outcome"],"STOP")
        self.assertEqual(out["close_r"],-1.0)


if __name__=="__main__":
    unittest.main()
