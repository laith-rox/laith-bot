import unittest
from v4_risk_advisor import risk_based_lot

class RiskAdvisorTests(unittest.TestCase):
    def test_valid_manual_lot(self):
        r = risk_based_lot(equity=1000, risk_percent=1, entry=4000,
                           stop=3995, contract_size=100, lot_step=.01,
                           min_lot=.01, max_lot=10)
        self.assertEqual(r["lot"], .02)
        self.assertEqual(r["estimated_stop_loss"], 10)
        self.assertTrue(r["manual_only"])

    def test_small_account_rejects_broker_minimum(self):
        self.assertIsNone(risk_based_lot(equity=10, risk_percent=1, entry=4000,
            stop=3995, contract_size=100, lot_step=.01, min_lot=.01, max_lot=10))

    def test_excessive_risk_rejected(self):
        self.assertIsNone(risk_based_lot(equity=1000, risk_percent=5, entry=4000,
            stop=3995, contract_size=100, lot_step=.01, min_lot=.01, max_lot=10))

    def test_invalid_or_unverified_spec_rejected(self):
        for size in (0, None, float('nan')):
            self.assertIsNone(risk_based_lot(equity=1000, risk_percent=1, entry=4000,
                stop=3995, contract_size=size, lot_step=.01, min_lot=.01, max_lot=10))

if __name__ == '__main__':
    unittest.main()
