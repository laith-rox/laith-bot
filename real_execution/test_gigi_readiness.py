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


if __name__=="__main__":
    unittest.main()
