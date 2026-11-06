import json
import unittest
from v4_verified_calendar import verified_sessions, verified_news

class CalendarAdapterTests(unittest.TestCase):
    def test_sessions_require_explicit_verification(self):
        sessions = [{"open": "2026-11-09T00:00:00Z", "close": "2026-11-09T23:00:00Z"}]
        self.assertEqual(verified_sessions(json.dumps({"sessions": sessions})), ())
        self.assertEqual(len(verified_sessions(json.dumps({"verified": True, "sessions": sessions}))), 1)

    def test_invalid_sessions_fail_closed(self):
        self.assertEqual(verified_sessions('not-json'), ())
        self.assertEqual(verified_sessions(json.dumps({"verified": True, "sessions": [{"open": "2026-11-09T23:00:00Z", "close": "2026-11-09T00:00:00Z"}]})), ())
        self.assertEqual(verified_sessions(json.dumps({"verified": True, "sessions": [{"open": "2026-11-09T00:00:00", "close": "2026-11-09T23:00:00Z"}]})), ())

    def test_news_requires_verification_and_timezone(self):
        event = {"id": "cpi", "title": "CPI", "importance": "high", "release_at": "2026-11-10T13:30:00Z"}
        self.assertEqual(verified_news(json.dumps({"events": [event]})), ())
        parsed = verified_news(json.dumps({"verified": True, "events": [event]}))
        self.assertEqual(len(parsed), 1)
        self.assertTrue(parsed[0]["calendar_verified"])
        self.assertIsNotNone(parsed[0]["release_at"].tzinfo)

if __name__ == "__main__":
    unittest.main()
