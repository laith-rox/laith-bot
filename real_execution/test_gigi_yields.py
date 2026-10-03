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


if __name__=="__main__":
    unittest.main()
