import unittest

import gigi_flow_divergence


class GigiFlowDivergenceTests(unittest.TestCase):
    def test_etf_inflow_vs_futures_deleveraging_is_explicit_divergence(self):
        out=gigi_flow_divergence.analyze(
            {"regime":"BROAD_INFLOW"},
            {"regime":"LONG_BIASED_DELEVERAGING"},
            {"h4_bias":"DOWN"},
        )
        self.assertEqual(out["state"],"ETF_BUYING_VS_FUTURES_LIQUIDATION")
        self.assertTrue(out["divergence"])
        self.assertEqual(out["price_alignment"],"PRICE_ALIGNS_FUTURES_LIQUIDATION")

    def test_confirmed_bullish_flow_is_not_divergence(self):
        out=gigi_flow_divergence.analyze(
            {"regime":"BROAD_INFLOW"},
            {"regime":"LONG_BIASED_ADDING"},
            {"h4_bias":"UP"},
        )
        self.assertEqual(out["state"],"FLOW_CONFIRMATION_BULLISH")
        self.assertFalse(out["divergence"])
        self.assertEqual(out["price_alignment"],"PRICE_CONFIRMS")

    def test_etf_outflow_vs_short_covering_is_divergence(self):
        out=gigi_flow_divergence.analyze(
            {"regime":"BROAD_OUTFLOW"},
            {"regime":"SHORT_BIASED_COVERING"},
            {"h4_bias":"UP"},
        )
        self.assertEqual(out["state"],"ETF_SELLING_VS_FUTURES_COVERING")
        self.assertTrue(out["divergence"])

    def test_no_directional_or_execution_authority(self):
        out=gigi_flow_divergence.analyze()
        self.assertFalse(out["directional_signal"])
        self.assertFalse(out["execution_gate"])


if __name__=="__main__":
    unittest.main()
