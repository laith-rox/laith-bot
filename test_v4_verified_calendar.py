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


class VerifiedEntryCalendarAvailabilityTests(unittest.TestCase):
    def test_missing_and_unverified_fail_closed(self):
        from v4_verified_calendar import verified_entry_calendar_available
        self.assertFalse(verified_entry_calendar_available(None))
        self.assertFalse(verified_entry_calendar_available(''))
        self.assertFalse(verified_entry_calendar_available('{}'))
        self.assertFalse(verified_entry_calendar_available('{"verified":false,"sessions":[]}'))
        self.assertFalse(verified_entry_calendar_available('{"verified":true,"sessions":[]}'))
        self.assertFalse(verified_entry_calendar_available('{"verified":true,"sessions":[{"open":"2026-11-07T00:00:00Z","close":"bad"}]}'))

    def test_explicit_valid_session_required(self):
        from v4_verified_calendar import verified_entry_calendar_available
        self.assertTrue(verified_entry_calendar_available('{"verified":true,"sessions":[{"open":"2026-11-09T00:00:00Z","close":"2026-11-09T22:00:00Z"}]}'))


class OverlappingBrokerSessionsTests(unittest.TestCase):
    def test_overlapping_sessions_fail_closed(self):
        from v4_verified_calendar import verified_entry_calendar_available
        sessions = [
            {"open": "2026-11-09T12:00:00Z", "close": "2026-11-09T18:00:00Z"},
            {"open": "2026-11-09T08:00:00Z", "close": "2026-11-09T13:00:00Z"},
        ]
        raw = json.dumps({"verified": True, "sessions": sessions})
        self.assertEqual(verified_sessions(raw), ())
        self.assertFalse(verified_entry_calendar_available(raw))

    def test_adjacent_sessions_are_allowed(self):
        sessions = [
            {"open": "2026-11-09T12:00:00Z", "close": "2026-11-09T18:00:00Z"},
            {"open": "2026-11-09T08:00:00Z", "close": "2026-11-09T12:00:00Z"},
        ]
        self.assertEqual(len(verified_sessions(json.dumps({"verified": True, "sessions": sessions}))), 2)


class NonObjectCalendarPayloadTests(unittest.TestCase):
    def test_json_scalar_and_list_fail_closed(self):
        from v4_verified_calendar import verified_entry_calendar_available
        for raw in ("null", "true", "[]", "42", "\"text\""):
            with self.subTest(raw=raw):
                self.assertEqual(verified_sessions(raw), ())
                self.assertEqual(verified_news(raw), ())
                self.assertFalse(verified_entry_calendar_available(raw))


class NewsIdentityIntegrityTests(unittest.TestCase):
    def test_duplicate_news_ids_fail_closed(self):
        events = [
            {"id": "cpi", "title": "CPI", "release_at": "2026-11-10T13:30:00Z"},
            {"id": "cpi", "title": "CPI revised", "release_at": "2026-11-10T14:30:00Z"},
        ]
        self.assertEqual(verified_news(json.dumps({"verified": True, "events": events})), ())

    def test_duplicate_news_ids_with_whitespace_and_case_fail_closed(self):
        events = [
            {"id": "CPI", "title": "CPI", "release_at": "2026-11-10T13:30:00Z"},
            {"id": " cpi ", "title": "Inflation revised", "release_at": "2026-11-10T14:30:00Z"},
        ]
        self.assertEqual(verified_news(json.dumps({"verified": True, "events": events})), ())

    def test_invalid_event_identity_and_blank_title_fail_closed(self):
        for changes in ({"id": []}, {"id": ""}, {"title": "  "}, {"title": 123}):
            with self.subTest(changes=changes):
                event = {"id": "cpi", "title": "CPI", "release_at": "2026-11-10T13:30:00Z"}
                event.update(changes)
                self.assertEqual(verified_news(json.dumps({"verified": True, "events": [event]})), ())

    def test_duplicate_release_without_ids_rejected(self):
        events = [
            {"title": "CPI", "release_at": "2026-11-10T13:30:00Z"},
            {"title": " cpi ", "release_at": "2026-11-10T13:30:00+00:00"},
        ]
        self.assertEqual(verified_news(json.dumps({"verified": True, "events": events})), ())

    def test_same_title_at_distinct_release_times_allowed(self):
        events = [
            {"title": "CPI", "release_at": "2026-11-10T13:30:00Z"},
            {"title": "CPI", "release_at": "2026-12-10T13:30:00Z"},
        ]
        self.assertEqual(len(verified_news(json.dumps({"verified": True, "events": events}))), 2)

    def test_distinct_news_ids_allowed(self):
        events = [
            {"id": "cpi", "title": "CPI", "release_at": "2026-11-10T13:30:00Z"},
            {"id": "ppi", "title": "PPI", "release_at": "2026-11-11T13:30:00Z"},
        ]
        self.assertEqual(len(verified_news(json.dumps({"verified": True, "events": events}))), 2)


class BrokerSessionDurationSafetyTests(unittest.TestCase):
    def test_weeklong_verified_session_cannot_authorize_weekend(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-06T00:00:00Z", "close": "2026-11-13T00:00:00Z"}]})
        self.assertEqual(verified_sessions(raw), ())

    def test_overnight_broker_session_under_24h_remains_valid(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-09T22:00:00Z", "close": "2026-11-10T21:00:00Z"}]})
        self.assertEqual(len(verified_sessions(raw)), 1)

    def test_long_session_invalidates_entire_calendar(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-09T00:00:00Z", "close": "2026-11-09T12:00:00Z"},
            {"open": "2026-11-10T00:00:00Z", "close": "2026-11-12T00:00:00Z"}]})
        self.assertEqual(verified_sessions(raw), ())


class SaturdayBrokerSessionGuardTests(unittest.TestCase):
    def test_rejects_verified_saturday_session(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-07T08:00:00Z", "close": "2026-11-07T10:00:00Z"}
        ]})
        self.assertEqual(verified_sessions(raw), ())

    def test_rejects_friday_session_crossing_into_saturday(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-06T23:30:00Z", "close": "2026-11-07T00:30:00Z"}
        ]})
        self.assertEqual(verified_sessions(raw), ())

    def test_allows_verified_friday_and_sunday_sessions(self):
        raw = json.dumps({"verified": True, "sessions": [
            {"open": "2026-11-06T21:00:00Z", "close": "2026-11-06T23:00:00Z"},
            {"open": "2026-11-08T22:00:00Z", "close": "2026-11-08T23:00:00Z"}
        ]})
        self.assertEqual(len(verified_sessions(raw)), 2)

