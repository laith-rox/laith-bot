from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from market import Market

UTC = timezone.utc


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        if not self.responses:
            raise AssertionError("unexpected provider request")
        return self.responses.pop(0)


def good_payload():
    return {
        "meta": {"symbol": "XAU/USD"},
        "values": [
            {"datetime": "2026-10-02 17:40:00", "open": "4000", "high": "4002", "low": "3999", "close": "4001"},
            {"datetime": "2026-10-02 17:45:00", "open": "4001", "high": "4004", "low": "4000", "close": "4003"},
            {"datetime": "2026-10-02 17:50:00", "open": "4003", "high": "4005", "low": "4002", "close": "4004"},
        ],
    }


class MarketRateLimitTests(unittest.TestCase):
    def test_candle_cache_is_close_to_five_minute_cycle(self):
        m = Market("x", session=FakeSession([]))
        self.assertGreaterEqual(m._bars_cache_ttl, 270)
        self.assertLessEqual(m._bars_cache_ttl, 300)

    def test_429_uses_recent_validated_cache_and_enters_backoff(self):
        now = datetime(2026, 10, 2, 18, 0, tzinfo=UTC)
        session = FakeSession([
            FakeResponse(200, good_payload()),
            FakeResponse(429),
        ])
        m = Market("x", session=session)
        with patch("market.time.monotonic", return_value=1000.0):
            first = m.fetch(now)
            m._bars_cache_at = 0.0
            second = m.fetch(now)
            state = m.status()
            third = m.fetch(now)

        self.assertEqual(first, second)
        self.assertEqual(second, third)
        self.assertEqual(session.calls, 2)
        self.assertTrue(state["barsStale"])
        self.assertTrue(state["backoffActive"])
        self.assertEqual(state["lastError"], "market_http_429")


if __name__ == "__main__":
    unittest.main()
