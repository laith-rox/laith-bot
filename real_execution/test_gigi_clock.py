import unittest

import gigi_clock


class GigiClockTests(unittest.TestCase):
    def test_october_uses_summer_offset_when_timezone_database_available(self):
        out=gigi_clock.context("2026-10-03T12:00:00Z")
        self.assertEqual(out["local_iso"][:16],"2026-10-03T15:00")
        self.assertEqual(out["utc_offset_hours"],3.0)

    def test_november_uses_winter_offset(self):
        out=gigi_clock.context("2026-11-03T12:00:00Z")
        self.assertEqual(out["local_iso"][:16],"2026-11-03T14:00")
        self.assertEqual(out["utc_offset_hours"],2.0)

    def test_entry_boundary_follows_palestine_local_clock(self):
        self.assertEqual(gigi_clock.local_minute("2026-11-03T02:59:00Z"),4*60+59)
        self.assertEqual(gigi_clock.local_minute("2026-11-03T03:00:00Z"),5*60)


if __name__=="__main__":
    unittest.main()
