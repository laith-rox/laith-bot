import unittest
from v4_manual_risk_budget import manual_risk_budget


class ManualRiskBudgetTests(unittest.TestCase):
    def calc(self, **changes):
        args = dict(side="BUY", entry=4000, stop=3995, risk_budget_usd=5,
                    contract_oz_per_lot=100, usd_per_quote_unit=1,
                    lot_step=0.01, min_lot=0.01, max_lot=50)
        args.update(changes)
        return manual_risk_budget(**args)

    def test_exact_risk_ceiling(self):
        result = self.calc()
        self.assertEqual(result["status"], "ADVISORY")
        self.assertEqual(result["lot_ceiling"], 0.01)
        self.assertEqual(result["estimated_stop_risk_usd"], 5)
        self.assertTrue(result["manual_only"])

    def test_rounds_down_never_exceeds_budget(self):
        result = self.calc(risk_budget_usd=14)
        self.assertEqual(result["lot_ceiling"], 0.02)
        self.assertLessEqual(result["estimated_stop_risk_usd"], 14)

    def test_fractional_step_boundary_never_rounds_up(self):
        result = self.calc(entry=4000, stop=3999, risk_budget_usd=0.299999999999,
                           contract_oz_per_lot=1, lot_step=0.1, min_lot=0.1)
        self.assertEqual(result["lot_ceiling"], 0.2)
        self.assertLessEqual(result["estimated_stop_risk_usd"], 0.299999999999)

    def test_exact_decimal_step_boundary(self):
        result = self.calc(entry=4000, stop=3999, risk_budget_usd=0.3,
                           contract_oz_per_lot=1, lot_step=0.1, min_lot=0.1)
        self.assertEqual(result["lot_ceiling"], 0.3)

    def test_minimum_lot_cannot_fit(self):
        self.assertEqual(self.calc(risk_budget_usd=4)["reason"],
                         "minimum_lot_exceeds_risk_budget")

    def test_missing_contract_specs_fail_closed(self):
        self.assertEqual(self.calc(contract_oz_per_lot=None)["status"], "WAIT")
        self.assertEqual(self.calc(usd_per_quote_unit=None)["status"], "WAIT")

    def test_invalid_stop_direction(self):
        self.assertEqual(self.calc(stop=4005)["reason"], "invalid_stop_direction")
        self.assertEqual(self.calc(side="SELL", stop=3995)["reason"], "invalid_stop_direction")
        self.assertEqual(self.calc(side="SELL", stop=4005)["status"], "ADVISORY")

    def test_boolean_broker_specs_never_authorize_lot(self):
        for field in ("entry", "stop", "risk_budget_usd", "contract_oz_per_lot",
                      "usd_per_quote_unit", "lot_step", "min_lot", "max_lot"):
            with self.subTest(field=field):
                result = self.calc(**{field: True})
                self.assertEqual(result["status"], "WAIT")
                self.assertTrue(result["manual_only"])

    def test_rejects_nonfinite_and_invalid_limits(self):
        self.assertEqual(self.calc(entry=float("nan"))["status"], "WAIT")
        self.assertEqual(self.calc(min_lot=1, max_lot=0.1)["status"], "WAIT")

if __name__ == "__main__":
    unittest.main()
