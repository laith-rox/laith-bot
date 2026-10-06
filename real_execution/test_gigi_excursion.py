import unittest

import gigi_excursion


def obs(i,close_r=0.2,mfe_r=0.8,mae_r=-0.4,**features):
    return {
        "id":f"x{i}",
        "close_r":close_r,
        "mfe_r":mfe_r,
        "mae_r":mae_r,
        "mode":"SNIPER",
        "reason":"demo",
        "setup_archetype":"TREND_CONTINUATION",
        "session":"DAY_SNIPER",
        "flow_stress_state":"BALANCED",
        **features,
    }


class GigiExcursionTests(unittest.TestCase):
    def test_small_group_stays_insufficient(self):
        out=gigi_excursion.summarize_values([obs(i) for i in range(5)])
        self.assertEqual(out["status"],"INSUFFICIENT_SAMPLE")

    def test_early_profit_heavy_detected(self):
        rows=[]
        for i in range(40):
            rows.append(obs(i,mfe_r=0.7 if i<34 else 1.1,mae_r=-0.4,close_r=0.15))
        out=gigi_excursion.summarize_values(rows)
        self.assertEqual(out["path_posture"],"EARLY_PROFIT_HEAVY")
        self.assertGreaterEqual(out["hit_0_5r"],0.70)
        self.assertLess(out["hit_1_0r"],0.45)

    def test_extension_capable_detected(self):
        rows=[]
        for i in range(40):
            mfe=1.7 if i<26 else 0.8
            rows.append(obs(i,mfe_r=mfe,mae_r=-0.3,close_r=0.5))
        out=gigi_excursion.summarize_values(rows)
        self.assertEqual(out["path_posture"],"EXTENSION_CAPABLE")
        self.assertGreaterEqual(out["hit_1_0r"],0.60)

    def test_report_groups_by_reason_without_directional_signal(self):
        rows=[obs(i,reason="A" if i<20 else "B") for i in range(40)]
        out=gigi_excursion.report(rows,min_samples=10)
        self.assertIn("A",out["groups"]["reason"])
        self.assertIn("B",out["groups"]["reason"])
        self.assertFalse(out["directional_signal"])
        self.assertFalse(out["execution_gate"])


if __name__=="__main__":
    unittest.main()
