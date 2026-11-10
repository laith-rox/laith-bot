from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest import TestCase
from unittest.mock import Mock, patch

import v4_runtime


class QuickWindowTests(TestCase):
    def local(self, hour, minute, month=11, day=10):
        return datetime(2026, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Hebron"))

    def test_boundaries_and_midnight_in_winter_and_summer(self):
        for month, day in ((11, 10), (7, 14)):
            for hour, minute, allowed in ((19, 59, False), (20, 0, True),
                    (23, 29, True), (23, 30, False), (0, 0, False), (4, 30, False)):
                now = self.local(hour, minute, month, day).astimezone(timezone.utc)
                self.assertEqual(v4_runtime.quick_entry_window(now), allowed)

    def test_weekend_stays_closed(self):
        self.assertFalse(v4_runtime.quick_entry_window(self.local(21, 0, 11, 14)))

    def test_outside_window_monitors_open_quicks_but_never_requests_entry(self):
        paper = object.__new__(v4_runtime.V4PaperResilientQuick)
        paper.market = Mock()
        paper.store = Mock()
        paper.store.get.return_value = None
        paper._advance_quicks = Mock()
        paper.news = Mock()
        now = self.local(23, 30)
        with patch.object(v4_runtime, "quick_market_bars", return_value=([], False)), \
             patch.object(v4_runtime, "analyze_v4", return_value={}), \
             patch.object(v4_runtime, "quick_entry_reference") as entry:
            paper.quick_cycle(now)
        paper._advance_quicks.assert_called_once_with([], now)
        entry.assert_not_called()
        paper.news.check.assert_not_called()
        paper.store.set.assert_any_call("v4_quick_last_block", "outside_quick_entry_window")
