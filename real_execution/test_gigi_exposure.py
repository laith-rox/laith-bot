import unittest

import gigi_exposure


class GigiExposureTests(unittest.TestCase):
    def test_main_and_sniper_can_coexist_but_are_visible(self):
        out=gigi_exposure.analyze(
            {
                "owned_buy_count":1,
                "owned_sell_count":0,
                "main_buy_count":1,
                "sniper_buy_count":0,
            },
            {"side":"BUY","mode":"SNIPER"},
        )
        self.assertEqual(out["stacking_state"],"LAYERED")
        self.assertEqual(out["cross_mode_same_side_count"],1)
        self.assertFalse(out["execution_gate"])

    def test_multiple_same_side_positions_are_concentration_not_block(self):
        out=gigi_exposure.analyze(
            {
                "owned_buy_count":3,
                "owned_sell_count":0,
                "main_buy_count":1,
                "sniper_buy_count":2,
            },
            {"side":"BUY","mode":"MAIN"},
        )
        self.assertEqual(out["stacking_state"],"HIGH_CONCENTRATION")
        self.assertIn("same_direction_risk_concentration",out["reasons"])
        self.assertFalse(out["execution_gate"])

    def test_opposite_position_is_visible(self):
        out=gigi_exposure.analyze(
            {"owned_buy_count":1,"owned_sell_count":1},
            {"side":"SELL","mode":"SNIPER"},
        )
        self.assertEqual(out["book_state"],"TWO_SIDED")
        self.assertEqual(out["opposite_side_open_count"],1)


if __name__=="__main__":
    unittest.main()
