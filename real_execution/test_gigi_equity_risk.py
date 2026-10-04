import unittest
import gigi_equity_risk


class GigiEquityRiskTests(unittest.TestCase):
    def test_ten_dollar_medium_sniper_cap(self):
        out=gigi_equity_risk.limits("SNIPER",5,10)
        self.assertEqual(out["per_trade_cap_usd"],0.20)
        self.assertEqual(out["global_open_risk_cap_usd"],1.00)

    def test_ten_dollar_strong_sniper_cap(self):
        out=gigi_equity_risk.limits("SNIPER",7,10)
        self.assertEqual(out["per_trade_cap_usd"],0.50)

    def test_main_uses_structural_location_but_money_cap_is_five_percent(self):
        out=gigi_equity_risk.limits("MAIN",7,10)
        self.assertEqual(out["per_trade_cap_usd"],0.50)

    def test_main_wide_stop_is_rejected_not_artificially_tightened(self):
        out=gigi_equity_risk.validate(2.0,0.0,"MAIN",7,10)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"per_trade_equity_cap_reject")

    def test_multiple_trades_obey_global_open_risk_cap(self):
        out=gigi_equity_risk.validate(0.5,0.7,"MAIN",7,10)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"global_equity_risk_cap_reject")


if __name__=="__main__":
    unittest.main()
