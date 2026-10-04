import unittest
import gigi_readiness


class GigiReadinessTests(unittest.TestCase):
    def base(self):
        return dict(
            signal={"side":"BUY"},
            quality={"quality":"HIGH"},
            execution_quality={"quality":"NORMAL"},
            thesis={"state":"CLEAN"},
            behavior={"state":"CLEAN"},
            stop_geometry={"noise_exposure":"LOW"},
            exposure={"stacking_state":"CLEAR"},
            context={"alignment":"SUPPORT"},
        )

    def test_clean_shadow_context(self):
        out=gigi_readiness.audit(**self.base())
        self.assertEqual(out["state"],"SHADOW_CLEAN")
        self.assertFalse(out["execution_gate"])

    def test_stale_tick_blocks_shadow_review(self):
        args=self.base()
        args["execution_quality"]={"quality":"STALE_TICK"}
        out=gigi_readiness.audit(**args)
        self.assertEqual(out["state"],"SHADOW_BLOCKED")
        self.assertIn("execution_quality_stale_tick",out["blockers"])

    def test_multiple_soft_problems_create_caution(self):
        args=self.base()
        args["quality"]={"quality":"LOW"}
        args["thesis"]={"state":"FRAGILE"}
        args["stop_geometry"]={"noise_exposure":"HIGH"}
        out=gigi_readiness.audit(**args)
        self.assertEqual(out["state"],"SHADOW_CAUTION")
        self.assertGreaterEqual(len(out["warnings"]),3)

    def test_no_side_is_blocked(self):
        args=self.base()
        args["signal"]={"side":None}
        out=gigi_readiness.audit(**args)
        self.assertEqual(out["state"],"SHADOW_BLOCKED")
        self.assertIn("no_directional_setup",out["blockers"])

    def test_negative_historical_prior_is_review_warning(self):
        args=self.base()
        args["price_prior"]={"status":"STABLE_NEGATIVE"}
        out=gigi_readiness.audit(**args)
        self.assertEqual(out["state"],"SHADOW_REVIEW")
        self.assertIn("historical_price_prior_negative",out["warnings"])

    def test_ambitious_target_and_lbma_window_raise_caution(self):
        args=self.base()
        args["target_geometry"]={
            "state":"AMBITION_HIGH",
            "implied_move_relation":"FAR_BEYOND_1D_PROXY",
        }
        args["benchmark"]={"phase":"AUCTION_OR_IMMEDIATE_POST"}
        out=gigi_readiness.audit(**args)
        self.assertEqual(out["state"],"SHADOW_CAUTION")
        self.assertIn("target_ambition_high",out["warnings"])
        self.assertIn("lbma_benchmark_window",out["warnings"])


    def test_stable_negative_price_prior_is_shadow_quarantined(self):
        out=gigi_readiness.audit(
            {"side":"BUY"},
            {"quality":"HIGH"},
            {"quality":"GOOD"},
            {"state":"CLEAN"},
            {"state":"CLEAR"},
            {"noise_exposure":"LOW"},
            {"stacking_state":"CLEAR"},
            {"alignment":"SUPPORT"},
            {"state":"NORMAL","implied_move_relation":"WITHIN_1D_PROXY"},
            {"status":"STABLE_NEGATIVE"},
            {"phase":"NORMAL"},
        )
        self.assertEqual(out["state"],"SHADOW_QUARANTINED")
        self.assertTrue(out["historical_quarantine"])
        self.assertIn("historical_reason_shadow_quarantine",out["warnings"])
        self.assertFalse(out["execution_gate"])



if __name__=="__main__":
    unittest.main()
