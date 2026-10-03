import unittest
from datetime import datetime, timezone, timedelta

import gigi_session_profile


def bars(start, count, step=0.05):
    out=[]
    price=100.0
    for i in range(count):
        dt=start+timedelta(minutes=5*i)
        o=price
        c=price+step
        out.append({
            "datetime":dt.isoformat().replace("+00:00","Z"),
            "open":o,
            "high":max(o,c)+0.10,
            "low":min(o,c)-0.10,
            "close":c,
            "tick_volume":100+i%7,
        })
        price=c
    return out


class GigiSessionProfileTests(unittest.TestCase):
    def test_new_york_anchor_is_dst_aware(self):
        # 2026-10-01 12:30 UTC is 08:30 New York (EDT).
        rows=bars(datetime(2026,10,1,0,0,tzinfo=timezone.utc),151)
        out=gigi_session_profile.analyze(rows)
        self.assertEqual(out["session"],"NEW_YORK")
        self.assertEqual(out["vwap_anchor"],"NEW_YORK_0820")
        self.assertIn(out["vwap_relation"],("ABOVE_ACCEPTANCE","BELOW_ACCEPTANCE","CROSSING"))

    def test_london_anchor_before_new_york(self):
        # 2026-10-01 08:30 UTC is 09:30 London (BST), before NY 08:20.
        rows=bars(datetime(2026,10,1,0,0,tzinfo=timezone.utc),103)
        out=gigi_session_profile.analyze(rows)
        self.assertEqual(out["session"],"LONDON")
        self.assertEqual(out["vwap_anchor"],"LONDON_0800")

    def test_failed_break_above_opening_range_is_visible(self):
        rows=bars(datetime(2026,10,1,0,0,tzinfo=timezone.utc),170,step=0.0)
        # At latest time NY opening range is complete. Force a wick above it
        # with close back inside.
        base=gigi_session_profile.analyze(rows)
        high=base["opening_range_high"]
        self.assertIsNotNone(high)
        rows[-1]["high"]=high+1.0
        rows[-1]["close"]=high-0.05
        out=gigi_session_profile.analyze(rows)
        self.assertEqual(out["opening_range_state"],"FAILED_BREAK_ABOVE")
        self.assertEqual(out["range_event"],"FAILED_BREAK_ABOVE")

    def test_vwap_is_explicit_tick_volume_proxy(self):
        rows=bars(datetime(2026,10,1,0,0,tzinfo=timezone.utc),151)
        out=gigi_session_profile.analyze(rows)
        self.assertIn("tick_volume_proxy",out["volume_note"])
        self.assertFalse(out["directional_signal"])

    def test_short_input_is_insufficient(self):
        out=gigi_session_profile.analyze([])
        self.assertEqual(out["data_quality"],"INSUFFICIENT")
        self.assertEqual(out["vwap_relation"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
