"""Prevent missing verified-news gate imports from breaking gold polling."""
import unittest

import v4_runtime


class GoldRuntimeNewsGateImportTests(unittest.TestCase):
    def test_news_calendar_gate_is_bound_in_runtime(self):
        self.assertTrue(callable(v4_runtime.verified_news_calendar_available))

    def test_unverified_news_still_blocks_gold(self):
        self.assertFalse(v4_runtime.verified_news_calendar_available(None))
        self.assertFalse(v4_runtime.verified_news_calendar_available('{"verified":false,"events":[]}'))

    def test_explicit_verified_empty_news_calendar_is_valid(self):
        self.assertTrue(v4_runtime.verified_news_calendar_available('{"verified":true,"events":[]}'))


if __name__ == '__main__':
    unittest.main()
