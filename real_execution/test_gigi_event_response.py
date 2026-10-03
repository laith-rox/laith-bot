import unittest
from datetime import datetime, timezone, timedelta

import gigi_event_response


def rows(event_time, closes):
    out=[]
    # Twenty pre-event M5 bars = 100 minutes, not 300 minutes.
    t0=event_time-timedelta(minutes=5*20)
    prev=100.0
    for i,c in enumerate(closes):
        t=t0+timedelta(minutes=5*i)
        c=float(c)
        out.append({
            "datetime":t.isoformat(),
            "open":prev,
            "high":max(prev,c)+0.2,
            "low":min(prev,c)-0.2,
            "close":c,
        })
        prev=c
    return out


class GigiEventResponseTests(unittest.TestCase):
    def test_pre_event_is_not_directional(self):
        out=gigi_event_response.analyze([],{
            "phase":"PRE_HIGH_EVENT",
            "near_high":[{"title":"CPI","time":1}],
        })
        self.assertEqual(out["state"],"PRE_EVENT")
        self.assertFalse(out["directional_signal"])

    def test_first_spike_is_untrusted(self):
        event=datetime(2026,10,5,12,30,tzinfo=timezone.utc)
        base=[100+0.02*i for i in range(20)]
        post=[102.0]
        out=gigi_event_response.analyze(
            rows(event,base+post),
            {"phase":"HIGH_EVENT_SHOCK_0_5M","near_high":[{"title":"NFP","time":event.timestamp()}]},
        )
        self.assertEqual(out["state"],"FIRST_SPIKE_UNTRUSTED")

    def test_confirmed_shock_keeps_direction(self):
        event=datetime(2026,10,5,12,30,tzinfo=timezone.utc)
        base=[100+0.02*i for i in range(20)]
        post=[102.0,102.3,102.5]
        out=gigi_event_response.analyze(
            rows(event,base+post),
            {"phase":"HIGH_EVENT_DIGESTION_5_15M","near_high":[{"title":"CPI","time":event.timestamp()}]},
        )
        self.assertEqual(out["state"],"SHOCK_CONFIRMED")
        self.assertEqual(out["impulse"],"BULLISH")

    def test_reversed_shock_is_detected(self):
        event=datetime(2026,10,5,12,30,tzinfo=timezone.utc)
        base=[100+0.02*i for i in range(20)]
        post=[102.0,100.1,99.7]
        out=gigi_event_response.analyze(
            rows(event,base+post),
            {"phase":"HIGH_EVENT_DIGESTION_5_15M","near_high":[{"title":"FOMC","time":event.timestamp()}]},
        )
        self.assertEqual(out["state"],"SHOCK_REVERSED")


if __name__=="__main__":
    unittest.main()
