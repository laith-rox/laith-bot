import unittest
from datetime import datetime, timezone, timedelta

import gigi_local_premium


def series(last=20.0):
    t0=datetime(2025,10,1,tzinfo=timezone.utc)
    out=[]
    for i in range(260):
        value=-20.0+(40.0*i/259.0)
        out.append([int((t0+timedelta(days=i)).timestamp()*1000),value])
    out[-1][1]=last
    return out


class GigiLocalPremiumTests(unittest.TestCase):
    def test_strong_china_premium_is_detected_by_own_history(self):
        out=gigi_local_premium.parse({"chartData":{
            "china_premdisc":series(30.0),
            "india_premdisc":series(-5.0),
            "asOfDate":"25 September, 2026",
        }})
        self.assertEqual(out["china"]["state"],"STRONG_PREMIUM")
        self.assertGreaterEqual(out["china"]["percentile_1y"],0.8)
        self.assertFalse(out["directional_signal"])

    def test_strong_discount_is_detected(self):
        out=gigi_local_premium.parse({"chartData":{
            "china_premdisc":series(-30.0),
            "india_premdisc":series(3.0),
        }})
        self.assertEqual(out["china"]["state"],"STRONG_DISCOUNT")

    def test_short_history_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"local_premium_history_too_short"):
            gigi_local_premium.parse({"chartData":{
                "china_premdisc":[[1,1.0]],
                "india_premdisc":[[1,1.0]],
            }})

    def test_note_says_not_trading_metric(self):
        out=gigi_local_premium.parse({"chartData":{
            "china_premdisc":series(10.0),
            "india_premdisc":series(5.0),
        }})
        self.assertIn("not_trading_metric",out["note"])


if __name__=="__main__":
    unittest.main()
