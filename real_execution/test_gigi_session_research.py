import unittest
from datetime import datetime,timezone,timedelta

import gigi_session_research


def make_rows(n=500, start=None):
    start=start or datetime(2026,9,1,tzinfo=timezone.utc)
    rows=[]
    price=4000.0
    for i in range(n):
        dt=start+timedelta(minutes=15*i)
        # deterministic alternating movement; no fake directional edge.
        step=(1.0 if i%2==0 else -0.7)
        op=price
        price=price+step
        rows.append({
            "datetime":dt.isoformat(),
            "open":op,
            "high":max(op,price)+0.4,
            "low":min(op,price)-0.4,
            "close":price,
        })
    return rows


class SessionResearchTests(unittest.TestCase):
    def test_descriptive_only(self):
        out=gigi_session_research.analyze(make_rows(),timezone_name="UTC",min_samples=1)
        self.assertEqual(out["state"],"READY")
        self.assertFalse(out["directional_signal"])
        self.assertFalse(out["execution_gate"])

    def test_gap_is_not_counted_as_forward_move(self):
        rows=make_rows(120)
        # Insert a weekend-like gap by shifting the later timestamps.
        for i in range(60,len(rows)):
            dt=datetime.fromisoformat(rows[i]["datetime"])+timedelta(days=2)
            rows[i]["datetime"]=dt.isoformat()
        out=gigi_session_research.analyze(rows,timezone_name="UTC",min_samples=1)
        total=sum(x["n"] for x in out["hours"].values())
        self.assertLess(total,120)

    def test_window_summary_wraps_midnight(self):
        p={"hours":{
            "19":{"quality":"USABLE","activity":"HIGH","behavior":"MIXED"},
            "22":{"quality":"USABLE","activity":"NORMAL","behavior":"REVERSAL_LEAN"},
            "4":{"quality":"USABLE","activity":"LOW","behavior":"CONTINUATION_LEAN"},
            "10":{"quality":"USABLE","activity":"HIGH","behavior":"CONTINUATION_LEAN"},
        }}
        out=gigi_session_research.window_summary(p,19,5)
        self.assertEqual(out["high_activity_hours"],[19])
        self.assertEqual(out["continuation_lean_hours"],[4])
        self.assertEqual(out["reversal_lean_hours"],[22])
        self.assertNotIn(10,out["high_activity_hours"])


if __name__=="__main__":
    unittest.main()
