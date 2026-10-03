import unittest
from datetime import datetime, timezone, timedelta

import gigi_regime


def rows(count, minutes, start=100.0, step=0.2, volume=100):
    out = []
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    price = start
    for i in range(count):
        o = price
        c = price + step
        high = max(o, c) + 0.15
        low = min(o, c) - 0.15
        out.append({
            "datetime": (t0 + timedelta(minutes=minutes*i)).isoformat(),
            "open": o,
            "high": high,
            "low": low,
            "close": c,
            "tick_volume": volume,
        })
        price = c
    return out


class GigiRegimeTests(unittest.TestCase):
    def test_uptrend_is_detected(self):
        m5 = rows(40, 5, step=0.08)
        m15 = rows(45, 15, step=0.12)
        h4 = rows(60, 240, step=0.50)
        result = gigi_regime.classify(m5, m15, h4)
        self.assertIn(result["name"], ("TREND_UP", "TREND_EXPANSION"))
        self.assertEqual(result["h4_bias"], "UP")

    def test_effort_without_result_marks_absorption(self):
        m5 = rows(40, 5, step=0.08, volume=100)
        # Last bar: very high effort, tiny range/result.
        m5[-1].update({
            "open": m5[-2]["close"],
            "close": m5[-2]["close"] + 0.01,
            "high": m5[-2]["close"] + 0.04,
            "low": m5[-2]["close"] - 0.03,
            "tick_volume": 250,
        })
        m15 = rows(45, 15, step=0.10)
        h4 = rows(60, 240, step=0.30)
        result = gigi_regime.classify(m5, m15, h4)
        self.assertEqual(result["effort_result"], "ABSORPTION")

    def test_short_inputs_fail_neutral(self):
        result = gigi_regime.classify([], [], [])
        self.assertEqual(result["name"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
