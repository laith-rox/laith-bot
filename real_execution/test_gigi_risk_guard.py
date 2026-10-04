import unittest
import gigi_risk_guard


class GigiRiskGuardTests(unittest.TestCase):
    def test_missing_hard_cap_fails_closed(self):
        out=gigi_risk_guard.validate(1,0,0,None,10,None)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"account_hard_risk_cap_unset")

    def test_main_without_mode_budget_still_obeys_account_cap(self):
        out=gigi_risk_guard.validate(2,1,1,2.5,10,None)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"account_hard_cap_reject")

    def test_sniper_obeys_mode_and_account_caps(self):
        out=gigi_risk_guard.validate(2,1,2,8,20,3)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"mode_risk_reject")

    def test_concurrent_modes_can_pass_when_global_cap_has_room(self):
        out=gigi_risk_guard.validate(1.5,2,0.5,5,20,3)
        self.assertTrue(out["ok"])
        self.assertEqual(out["reason"],"approved")

    def test_equity_is_absolute_last_ceiling(self):
        out=gigi_risk_guard.validate(4,6,1,20,10,None)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"total_risk_exceeds_equity")


if __name__=="__main__":
    unittest.main()
