import io
import json
import unittest
from datetime import datetime, timezone
from v4_free_news_calendar import fetch_verified_news
from v4_verified_calendar import verified_news_calendar_available

NOW = datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc)

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
                          "impact": "high", "time": "2026-11-11T13:30:00Z",
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
    def test_empty_verified_calendar_is_valid(self):
        raw = fetch_verified_news(NOW, provider(payload(events=[])))
        self.assertTrue(verified_news_calendar_available(raw))
    def test_malformed_fails_closed(self):
        with self.assertRaises(ValueError):
            fetch_verified_news(NOW, provider(payload(events="bad")))

if __name__ == "__main__":
    unittest.main()
