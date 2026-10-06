import unittest
from datetime import datetime,timezone,timedelta

import gigi_flow_stress


def make_rows(direction="flat"):
    start=datetime(2026,10,6,8,0,tzinfo=timezone.utc)
    rows=[]
    price=4000.0
    for i in range(30):
        op=price
        if i < 26:
            step=0.10 if i%2==0 else -0.08
            vol=100
            pad=0.35
        else:
            if direction=="up":
                step=1.20
            elif direction=="down":
                step=-1.20
            elif direction=="fast_up":
                step=0.65
            else:
                step=0.02 if i%2==0 else -0.02
            vol=160 if direction in ("up","down") else 100
            pad=0.15 if direction in ("up","down","fast_up") else 0.35
        close=op+step
        rows.append({
            "datetime":(start+timedelta(minutes=5*i)).isoformat(),
            "open":op,
            "high":max(op,close)+pad,
            "low":min(op,close)-pad,
            "close":close,
            "tick_volume":vol,
        })
        price=close
    return rows


class GigiFlowStressTests(unittest.TestCase):
    def test_up_squeeze_detected(self):
        out=gigi_flow_stress.analyze(make_rows("up"))
        self.assertEqual(out["state"],"UP_SQUEEZE")
        self.assertEqual(out["direction"],"UP")
        self.assertGreaterEqual(out["cascade_score"],4)
        self.assertFalse(out["directional_signal"])

    def test_down_cascade_detected(self):
        out=gigi_flow_stress.analyze(make_rows("down"))
        self.assertEqual(out["state"],"DOWN_CASCADE")
        self.assertEqual(out["direction"],"DOWN")
        self.assertGreaterEqual(out["cascade_score"],4)

    def test_balanced_market_is_not_forced_direction(self):
        out=gigi_flow_stress.analyze(make_rows("flat"))
        self.assertEqual(out["state"],"BALANCED")
        self.assertEqual(out["direction"],"NONE")

    def test_short_history_fails_neutral(self):
        out=gigi_flow_stress.analyze([])
        self.assertEqual(out["state"],"UNKNOWN")
        self.assertFalse(out["directional_signal"])


if __name__=="__main__":
    unittest.main()
