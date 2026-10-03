import unittest
from datetime import datetime, timezone

import gigi_macro


class GigiMacroTests(unittest.TestCase):
    def test_parse_keeps_usd_medium_and_high_only(self):
        payload = [
            {"country":"USD","impact":"High","title":"CPI","date":"2026-10-05T12:30:00+00:00"},
            {"country":"USD","impact":"Medium","title":"Factory Orders","date":"2026-10-05T14:00:00+00:00"},
            {"country":"EUR","impact":"High","title":"ECB","date":"2026-10-05T12:45:00+00:00"},
            {"country":"USD","impact":"Low","title":"Minor","date":"2026-10-05T15:00:00+00:00"},
        ]
        events = gigi_macro.parse_events(payload)
        self.assertEqual([e["title"] for e in events], ["CPI","Factory Orders"])

    def test_high_impact_window_is_detected(self):
        now = datetime(2026,10,5,12,15,tzinfo=timezone.utc).timestamp()
        events = [{
            "title":"CPI",
            "impact":"HIGH",
            "time":datetime(2026,10,5,12,30,tzinfo=timezone.utc).timestamp(),
        }]
        out = gigi_macro.context(now, events, None)
        self.assertEqual(out["regime"], "HIGH_IMPACT_WINDOW")
        self.assertEqual(out["near_high"][0]["title"], "CPI")

    def test_clear_when_no_near_events(self):
        now = datetime(2026,10,5,12,0,tzinfo=timezone.utc).timestamp()
        events = [{
            "title":"CPI",
            "impact":"HIGH",
            "time":datetime(2026,10,5,15,0,tzinfo=timezone.utc).timestamp(),
        }]
        out = gigi_macro.context(now, events, None)
        self.assertEqual(out["regime"], "CLEAR")

    def test_unknown_without_calendar(self):
        out = gigi_macro.context(0, [], "calendar_unavailable")
        self.assertEqual(out["regime"], "UNKNOWN")

    def test_high_event_shock_phase_is_distinct_from_pre_event(self):
        event_time = datetime(2026,10,5,12,30,tzinfo=timezone.utc).timestamp()
        events = [{"title":"NFP","impact":"HIGH","time":event_time}]
        pre = gigi_macro.context(event_time - 10*60, events, None)
        shock = gigi_macro.context(event_time + 2*60, events, None)
        digest = gigi_macro.context(event_time + 10*60, events, None)
        self.assertEqual(pre["phase"], "PRE_HIGH_EVENT")
        self.assertEqual(shock["phase"], "HIGH_EVENT_SHOCK_0_5M")
        self.assertEqual(digest["phase"], "HIGH_EVENT_DIGESTION_5_15M")



if __name__ == "__main__":
    unittest.main()
