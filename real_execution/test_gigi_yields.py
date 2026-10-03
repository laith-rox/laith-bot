import unittest
from datetime import datetime, timezone

import gigi_yields


def nominal_xml():
    rows=[]
    vals=[
        ("25-SEP-26",3.60,4.10),
        ("28-SEP-26",3.62,4.12),
        ("29-SEP-26",3.65,4.13),
        ("30-SEP-26",3.69,4.15),
        ("01-OCT-26",3.73,4.18),
        ("02-OCT-26",3.76,4.20),
    ]
    for d,y2,y10 in vals:
        rows.append(f"<G_NEW_DATE><BID_CURVE_DATE>{d}</BID_CURVE_DATE><BC_2YEAR>{y2}</BC_2YEAR><BC_10YEAR>{y10}</BC_10YEAR></G_NEW_DATE>")
    return "<ROOT>"+"".join(rows)+"</ROOT>"


def real_xml():
    rows=[]
    vals=[
        ("25-SEP-26",1.45),
        ("28-SEP-26",1.47),
        ("29-SEP-26",1.50),
        ("30-SEP-26",1.52),
        ("01-OCT-26",1.55),
        ("02-OCT-26",1.58),
    ]
    for d,y in vals:
        rows.append(f"<G_NEW_DATE><TIPS_CURVE_DATE>{d}</TIPS_CURVE_DATE><TC_10YEAR>{y}</TC_10YEAR></G_NEW_DATE>")
    return "<ROOT>"+"".join(rows)+"</ROOT>"


class GigiYieldTests(unittest.TestCase):
    def test_rising_real_yield_regime(self):
        now=datetime(2026,10,3,tzinfo=timezone.utc).timestamp()
        out=gigi_yields.parse(nominal_xml(),real_xml(),now=now)
        self.assertEqual(out["real_yield_regime"],"RISING_REAL_YIELD")
        self.assertEqual(out["policy_regime"],"RISING_FRONT_END")
        self.assertAlmostEqual(out["real_10y"],1.58)

    def test_stale_feed_fails_context_closed(self):
        now=datetime(2026,10,20,tzinfo=timezone.utc).timestamp()
        out=gigi_yields.parse(nominal_xml(),real_xml(),now=now)
        self.assertEqual(out["real_yield_regime"],"STALE")
        self.assertFalse(out["directional_signal"])

    def test_curve_is_calculated(self):
        now=datetime(2026,10,3,tzinfo=timezone.utc).timestamp()
        out=gigi_yields.parse(nominal_xml(),real_xml(),now=now)
        self.assertAlmostEqual(out["curve_10y_minus_2y_bps"],44.0)

    def test_short_history_rejected(self):
        with self.assertRaisesRegex(ValueError,"treasury_history_too_short"):
            gigi_yields.parse("<ROOT/>","<ROOT/>")

    def test_two_sessions_do_not_masquerade_as_five_day_trend(self):
        nom="<ROOT><G_NEW_DATE><BID_CURVE_DATE>01-OCT-26</BID_CURVE_DATE><BC_2YEAR>4.70</BC_2YEAR><BC_10YEAR>5.20</BC_10YEAR></G_NEW_DATE><G_NEW_DATE><BID_CURVE_DATE>02-OCT-26</BID_CURVE_DATE><BC_2YEAR>4.83</BC_2YEAR><BC_10YEAR>5.28</BC_10YEAR></G_NEW_DATE></ROOT>"
        real="<ROOT><G_NEW_DATE><TIPS_CURVE_DATE>01-OCT-26</TIPS_CURVE_DATE><TC_10YEAR>2.88</TC_10YEAR></G_NEW_DATE><G_NEW_DATE><TIPS_CURVE_DATE>02-OCT-26</TIPS_CURVE_DATE><TC_10YEAR>2.92</TC_10YEAR></G_NEW_DATE></ROOT>"
        now=datetime(2026,10,3,tzinfo=timezone.utc).timestamp()
        out=gigi_yields.parse(nom,real,now=now)
        self.assertEqual(out["real_yield_regime"],"INSUFFICIENT_HISTORY")
        self.assertEqual(out["policy_regime"],"INSUFFICIENT_HISTORY")
        self.assertIsNone(out["real_10y_change_5d_bps"])
        self.assertIsNone(out["nominal_2y_change_5d_bps"])


    def test_year_csv_provides_real_five_session_context(self):
        nominal = """Date,2 Yr,10 Yr
09/25/2026,4.60,5.10
09/28/2026,4.62,5.12
09/29/2026,4.65,5.13
09/30/2026,4.69,5.15
10/01/2026,4.78,5.24
10/02/2026,4.83,5.28
"""
        real = """Date,5 YR,7 YR,10 YR,20 YR,30 YR
09/25/2026,2.64,2.73,2.83,3.08,3.22
09/28/2026,2.73,2.80,2.90,3.14,3.28
09/29/2026,2.72,2.80,2.91,3.15,3.29
09/30/2026,2.73,2.82,2.93,3.18,3.33
10/01/2026,2.65,2.76,2.88,3.16,3.31
10/02/2026,2.69,2.80,2.92,3.19,3.34
"""
        now=datetime(2026,10,3,tzinfo=timezone.utc).timestamp()
        out=gigi_yields.parse_csv(nominal,real,now=now)
        self.assertEqual(out["real_history_sessions"],6)
        self.assertEqual(out["nominal_history_sessions"],6)
        self.assertEqual(out["real_yield_regime"],"STABLE_REAL_YIELD")
        self.assertEqual(out["policy_regime"],"RISING_FRONT_END")
        self.assertAlmostEqual(out["nominal_2y_change_5d_bps"],23.0)



if __name__=="__main__":
    unittest.main()
