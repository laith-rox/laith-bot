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


    def test_event_classes_split_cpi_nfp_and_fomc(self):
        self.assertEqual(gigi_macro.event_class("CPI m/m"), "CPI")
        self.assertEqual(gigi_macro.event_class("Non-Farm Employment Change"), "LABOR_NFP")
        self.assertEqual(gigi_macro.event_class("FOMC Statement"), "FOMC_FED")
        self.assertEqual(gigi_macro.event_class("Fed Chair Powell Speaks"), "FOMC_FED")

    def test_context_exposes_active_event_class(self):
        event_time = datetime(2026,10,5,12,30,tzinfo=timezone.utc).timestamp()
        events = [{
            "title":"CPI m/m",
            "event_class":"CPI",
            "impact":"HIGH",
            "time":event_time,
        }]
        out = gigi_macro.context(event_time - 10*60, events, None)
        self.assertEqual(out["active_event_class"], "CPI")
        self.assertEqual(out["active_event_impact"], "HIGH")



    def test_simultaneous_nfp_components_are_one_event_bundle(self):
        event_time = datetime(2026,10,2,12,30,tzinfo=timezone.utc).timestamp()
        events = [
            {"title":"Non-Farm Employment Change","event_class":"LABOR_NFP","impact":"HIGH","time":event_time},
            {"title":"Unemployment Rate","event_class":"LABOR_NFP","impact":"HIGH","time":event_time},
            {"title":"Average Hourly Earnings m/m","event_class":"LABOR_NFP","impact":"HIGH","time":event_time},
        ]
        out = gigi_macro.context(event_time - 5*60, events, None)
        self.assertEqual(out["event_bundle_state"], "MULTI_HIGH_RELEASE")
        self.assertEqual(out["event_bundle_size"], 3)
        self.assertEqual(out["event_bundle_high_count"], 3)
        self.assertEqual(out["event_bundle_classes"], ["LABOR_NFP"])

    def test_single_cpi_stays_single_release(self):
        event_time = datetime(2026,10,5,12,30,tzinfo=timezone.utc).timestamp()
        events = [{"title":"CPI m/m","event_class":"CPI","impact":"HIGH","time":event_time}]
        out = gigi_macro.context(event_time - 5*60, events, None)
        self.assertEqual(out["event_bundle_state"], "SINGLE_RELEASE")
        self.assertEqual(out["event_bundle_size"], 1)


    def test_exhausted_weekly_calendar_is_not_false_clear(self):
        last = datetime(2026,10,2,14,0,tzinfo=timezone.utc).timestamp()
        now = datetime(2026,10,4,0,0,tzinfo=timezone.utc).timestamp()
        events = [{"title":"ISM","event_class":"ISM","impact":"MEDIUM","time":last}]
        out = gigi_macro.context(now, events, None)
        self.assertEqual(out["calendar_horizon"], "EXHAUSTED")
        self.assertEqual(out["regime"], "HORIZON_EXHAUSTED")
        self.assertEqual(out["phase"], "OUT_OF_HORIZON")



if __name__ == "__main__":
    unittest.main()
