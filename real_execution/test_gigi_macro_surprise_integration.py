import unittest
import gigi_context
import gigi_thesis

class GigiMacroSurpriseIntegrationTests(unittest.TestCase):
    def test_context_exposes_macro_surprise_without_extra_direction_score(self):
        out=gigi_context.evaluate(
            "BUY",
            {"name":"RANGE","h4_bias":"NEUTRAL","effort_result":"BALANCED"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            macro_surprise={
                "bundle_surprise":"USD_POSITIVE",
                "price_relation":"GOLD_REJECTED_USD_POSITIVE_SURPRISE",
            },
        )
        self.assertEqual(out["macro_surprise_bundle"],"USD_POSITIVE")
        self.assertIn("macro_price_rejected_textbook_direction",out["reasons"])
        self.assertEqual(out["score"],0)

    def test_thesis_marks_macro_price_divergence_as_uncertainty(self):
        out=gigi_thesis.audit(
            {"side":"BUY","risk_distance":3.0},
            {"h4_bias":"UP"},
            {"bias":"NEUTRAL"},
            {"regime":"CLEAR"},
            {"pressure":"NEUTRAL"},
            macro_surprise={
                "bundle_surprise":"USD_POSITIVE",
                "price_relation":"GOLD_REJECTED_USD_POSITIVE_SURPRISE",
            },
        )
        self.assertIn("macro_price_rejected_textbook_direction",out["uncertainty"])
        self.assertNotIn("macro_price_rejected_textbook_direction",out["conflicts"])

if __name__=="__main__":
    unittest.main()
