import unittest

import gigi_positioning

SAMPLE = """
GOLD - COMMODITY EXCHANGE INC. Code-088691
Disaggregated Commitments of Traders - Futures Only, September 29, 2026
All  :   406,456:    18,200     39,463     14,835    244,539     25,796    131,711     11,393     36,294    118,025     19,711     12,811:   48,784    16,449
Changes in Commitments from: September 22, 2026
:    -6,344:       481     -5,033        209     -6,213        683     -3,988      3,083      3,418       -258       -108     -3,236:   -3,653     1,062
MICRO GOLD - COMMODITY EXCHANGE INC.
"""


class GigiPositioningTests(unittest.TestCase):
    def test_parse_current_style_cftc_report(self):
        out = gigi_positioning.parse_gold_report(SAMPLE)
        self.assertEqual(out["managed_money_net"], 120318)
        self.assertEqual(out["managed_money_net_change"], -7071)
        self.assertEqual(out["regime"], "LONG_BIASED_DELEVERAGING")
        self.assertEqual(out["open_interest"], 406456)

    def test_crowding_uses_open_interest_not_raw_contract_count(self):
        out = gigi_positioning.parse_gold_report(SAMPLE)
        self.assertAlmostEqual(out["managed_money_net_oi"], 120318/406456, places=4)
        self.assertEqual(out["crowding"], "NORMAL")

    def test_missing_gold_section_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "gold_section_missing"):
            gigi_positioning.parse_gold_report("no gold here")


if __name__ == "__main__":
    unittest.main()
