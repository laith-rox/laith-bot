import unittest
from datetime import datetime, timezone

import gigi_quality


NOW=datetime(2026,10,3,12,0,tzinfo=timezone.utc).timestamp()


class GigiQualityTests(unittest.TestCase):
    def test_high_when_all_expected_sources_are_fresh(self):
        out=gigi_quality.assess(
            {"report_date":"September 29, 2026"},
            {"as_of":"2026-09-25"},
            {"gvz_date":"10/02/2026"},
            {"as_of":"2026-10-03 03:43:53"},
            {"as_of":"2026-10-02"},
            {"regime":"CLEAR","calendar_error":None},
            now=NOW,
            local_premium={"as_of":"2026-09-25"},
        )
        self.assertEqual(out["quality"],"HIGH")
        self.assertEqual(out["stale_sources"],[])

    def test_stale_and_missing_sources_lower_quality(self):
        out=gigi_quality.assess(
            {"report_date":"September 01, 2026"},
            {},
            {"gvz_date":"09/01/2026"},
            {},
            {"as_of":"2026-10-02"},
            {"regime":"UNKNOWN","calendar_error":"calendar_unavailable"},
            now=NOW,
            local_premium={},
        )
        self.assertEqual(out["quality"],"LOW")
        self.assertIn("cftc",out["stale_sources"])
        self.assertIn("etf",out["missing_sources"])

    def test_weekend_daily_sources_are_not_falsely_stale(self):
        out=gigi_quality.assess(
            {"report_date":"September 29, 2026"},
            {"as_of":"2026-09-25"},
            {"gvz_date":"10/02/2026"},
            {"as_of":"2026-10-03 03:43:53"},
            {"as_of":"2026-10-02"},
            {"regime":"CLEAR"},
            now=NOW,
            local_premium={"as_of":"2026-09-25"},
        )
        self.assertLess(out["ages_days"]["gvz"],2)
        self.assertLess(out["ages_days"]["yields"],2)

    def test_exhausted_macro_horizon_is_not_counted_as_available(self):
        out=gigi_quality.assess(
            {"report_date":"September 29, 2026"},
            {"as_of":"2026-09-25"},
            {"gvz_date":"10/02/2026"},
            {"as_of":"2026-10-03 03:43:53"},
            {"as_of":"2026-10-02"},
            {"regime":"HORIZON_EXHAUSTED","calendar_horizon":"EXHAUSTED","calendar_error":None},
            now=NOW,
            local_premium={"as_of":"2026-09-25"},
        )
        self.assertIn("macro",out["missing_sources"])
        self.assertNotIn("macro",out["available_sources"])


    def test_stale_local_premium_is_reported(self):
        out=gigi_quality.assess(
            {"report_date":"September 29, 2026"},
            {"as_of":"2026-09-25"},
            {"gvz_date":"10/02/2026"},
            {"as_of":"2026-10-03 03:43:53"},
            {"as_of":"2026-10-02"},
            {"regime":"CLEAR"},
            now=NOW,
            local_premium={"as_of":"2026-08-01"},
        )
        self.assertIn("local_premium",out["stale_sources"])



if __name__=="__main__":
    unittest.main()
