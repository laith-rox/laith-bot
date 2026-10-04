import unittest
import gigi_replay


class GigiReplayTests(unittest.TestCase):
    def test_buy_target_first(self):
        out=gigi_replay.first_touch_outcome(
            "BUY",100,2,1.5,
            [{"high":103.2,"low":99.5,"close":102.8}],
        )
        self.assertEqual(out["outcome"],"TARGET")
        self.assertEqual(out["close_r"],1.5)

    def test_same_bar_stop_and_target_counts_stop_conservatively(self):
        out=gigi_replay.first_touch_outcome(
            "BUY",100,2,1,
            [{"high":103,"low":97,"close":101}],
        )
        self.assertEqual(out["outcome"],"STOP")
        self.assertEqual(out["close_r"],-1.0)

    def test_sell_horizon_marks_to_market(self):
        out=gigi_replay.first_touch_outcome(
            "SELL",100,4,2,
            [{"high":101,"low":98,"close":99},{"high":101,"low":96.5,"close":97}],
        )
        self.assertEqual(out["outcome"],"HORIZON")
        self.assertAlmostEqual(out["close_r"],0.75,places=4)

    def test_summary_drawdown_and_split(self):
        obs=[
            {"resolved":True,"close_r":1.0,"outcome":"TARGET","mfe_r":1,"mae_r":-0.2,"time":1},
            {"resolved":True,"close_r":-1.0,"outcome":"STOP","mfe_r":0.2,"mae_r":-1,"time":2},
            {"resolved":True,"close_r":-1.0,"outcome":"STOP","mfe_r":0.1,"mae_r":-1,"time":3},
            {"resolved":True,"close_r":2.0,"outcome":"TARGET","mfe_r":2,"mae_r":-0.1,"time":4},
        ]
        s=gigi_replay.summarize(obs)
        self.assertEqual(s["n"],4)
        self.assertEqual(s["max_drawdown_r"],2.0)
        split=gigi_replay.chronological_split(obs,0.5)
        self.assertEqual(len(split["train"]),2)
        self.assertEqual(len(split["holdout"]),2)

    def test_summary_exposes_expectancy_math(self):
        obs=[
            {"resolved":True,"close_r":1.0,"outcome":"TARGET","mfe_r":1.2,"mae_r":-0.2},
            {"resolved":True,"close_r":1.0,"outcome":"TARGET","mfe_r":1.1,"mae_r":-0.1},
            {"resolved":True,"close_r":-1.0,"outcome":"STOP","mfe_r":0.2,"mae_r":-1.0},
        ]
        s=gigi_replay.summarize(obs)
        self.assertAlmostEqual(s["avg_win_r"],1.0,places=4)
        self.assertAlmostEqual(s["avg_loss_r"],-1.0,places=4)
        self.assertAlmostEqual(s["payoff_ratio"],1.0,places=4)
        self.assertAlmostEqual(s["profit_factor"],2.0,places=4)
        self.assertAlmostEqual(s["breakeven_win_rate"],0.5,places=4)

    def test_high_win_rate_can_still_have_negative_expectancy(self):
        obs=[
            *[{"resolved":True,"close_r":0.2,"outcome":"HORIZON","mfe_r":0.4,"mae_r":-0.2} for _ in range(6)],
            *[{"resolved":True,"close_r":-1.0,"outcome":"STOP","mfe_r":0.1,"mae_r":-1.0} for _ in range(4)],
        ]
        s=gigi_replay.summarize(obs)
        self.assertEqual(s["win_rate"],0.6)
        self.assertLess(s["mean_r"],0.0)
        self.assertLess(s["payoff_ratio"],1.0)



if __name__=="__main__":
    unittest.main()
