import io
import json
import unittest
from datetime import datetime, timezone, timedelta
from v4_free_news_calendar import fetch_verified_news
from v4_verified_calendar import verified_news_calendar_available

NOW = datetime.now(timezone.utc)
RELEASE = (NOW + timedelta(hours=8)).isoformat()

class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

def provider(data):
    def open_(request, timeout):
        return Response(json.dumps(data).encode())
    return open_

def payload(**changes):
    result = {"server_time": NOW.timestamp(), "generated_at": NOW.isoformat(),
              "events": [{"id": "usd-cpi.1", "title": "CPI", "currency": "USD",
                          "impact": "high", "time": RELEASE,
                          "status": "scheduled", "confidence": "official"}]}
    result.update(changes)
    return result

class FreeNewsTests(unittest.TestCase):
    def test_valid_news_calendar(self):
        raw = fetch_verified_news(NOW, provider(payload()))
        self.assertTrue(verified_news_calendar_available(raw))
    def test_stale_clock_fails_closed(self):
        with self.assertRaises(ValueError):
            fetch_verified_news(NOW, provider(payload(server_time=NOW.timestamp()-3600)))
    def test_uncertain_event_fails_closed(self):
        bad = payload()
        bad["events"][0]["confidence"] = "sources_disagree"
        with self.assertRaises(ValueError):
            fetch_verified_news(NOW, provider(bad))
    def test_tentative_release_fails_closed(self):
        bad = payload()
        bad["events"][0]["status"] = "tentative"
        with self.assertRaisesRegex(ValueError, "uncertain_calendar_event status=tentative confidence=official"):
            fetch_verified_news(NOW, provider(bad))
    def test_missing_confidence_fails_closed(self):
        bad = payload()
        del bad["events"][0]["confidence"]
        with self.assertRaisesRegex(ValueError, "uncertain_calendar_event"):
            fetch_verified_news(NOW, provider(bad))
    def test_naive_release_fails_closed(self):
        bad = payload()
        bad["events"][0]["time"] = (NOW + timedelta(hours=8)).replace(tzinfo=None).isoformat()
        with self.assertRaisesRegex(ValueError, "naive_release_time"):
            fetch_verified_news(NOW, provider(bad))
    def test_count_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "calendar_count_mismatch"):
            fetch_verified_news(NOW, provider(payload(count=2)))
    def test_duplicate_events_do_not_verify(self):
        bad = payload()
        bad["events"] = [bad["events"][0], dict(bad["events"][0])]
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_calendar_event"):
            fetch_verified_news(NOW, provider(bad))
    def test_duplicate_ids_fail_before_publication(self):
        bad = payload()
        duplicate = dict(bad["events"][0], title="Other USD release", time=(NOW + timedelta(hours=9)).isoformat())
        bad["events"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_calendar_event"):
            fetch_verified_news(NOW, provider(bad))
    def test_duplicate_release_with_different_ids_fails(self):
        bad = payload()
        bad["events"].append(dict(bad["events"][0], id="other-id"))
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_calendar_event"):
            fetch_verified_news(NOW, provider(bad))
    def test_null_event_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid_calendar_event"):
            fetch_verified_news(NOW, provider(payload(events=[None])))
    def test_old_release_fails_closed(self):
        bad = payload()
        bad["events"][0]["time"] = (NOW - timedelta(days=10)).isoformat()
        with self.assertRaisesRegex(ValueError, "release_outside_calendar_window"):
            fetch_verified_news(NOW, provider(bad))
    def test_far_future_release_fails_closed(self):
        bad = payload()
        bad["events"][0]["time"] = (NOW + timedelta(days=10)).isoformat()
        with self.assertRaisesRegex(ValueError, "release_outside_calendar_window"):
            fetch_verified_news(NOW, provider(bad))
    def test_empty_verified_calendar_is_valid(self):
        raw = fetch_verified_news(NOW, provider(payload(events=[])))
        self.assertTrue(verified_news_calendar_available(raw))
    def test_malformed_fails_closed(self):
        with self.assertRaises(ValueError):
            fetch_verified_news(NOW, provider(payload(events="bad")))

if __name__ == "__main__":
    unittest.main()
