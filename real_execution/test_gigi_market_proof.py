import unittest
import gigi_market_proof

class GigiMarketProofTests(unittest.TestCase):
    def test_sniper_is_multi_window_negative(self):
        out=gigi_market_proof.assess("SNIPER","unknown")
        self.assertEqual(out["mode_status"],"STABLE_NEGATIVE")
        self.assertEqual(out["proof_state"],"MARKET_PROVEN_CAUTION")
        self.assertLess(out["mode_weighted_mean_r"],0)

    def test_main_is_promising_but_not_called_proven(self):
        out=gigi_market_proof.assess("MAIN","unknown")
        self.assertEqual(out["mode_status"],"PROMISING_UNSTABLE")
        self.assertEqual(out["proof_state"],"PROMISING_NOT_PROVEN")
        self.assertGreater(out["mode_weighted_mean_r"],0)

    def test_negative_reason_keeps_caution_even_in_main(self):
        out=gigi_market_proof.assess("MAIN","fast_primary_2of3")
        self.assertEqual(out["reason_status"],"STABLE_NEGATIVE")
        self.assertEqual(out["proof_state"],"MARKET_PROVEN_CAUTION")

    def test_never_authorizes_execution(self):
        out=gigi_market_proof.assess("MAIN","x")
        self.assertFalse(out["execution_gate"])
        self.assertFalse(out["directional_signal"])

if __name__=="__main__":
    unittest.main()
