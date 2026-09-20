import unittest

from bridge_signal_worker import compute_signal, normalize_rows


def make_values(direction="up"):
    rows = []
    price = 4300.0
    for i in range(42):
        step = 1.2 if direction == "up" else -1.2
        open_ = price
        close = price + step
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.35
        rows.append({
            "datetime": f"2026-09-21 {i//12:02d}:{(i%12)*5:02d}:00",
            "open": f"{open_:.2f}",
            "high": f"{high:.2f}",
            "low": f"{low:.2f}",
            "close": f"{close:.2f}",
        })
        price = close
    # Twelve Data returns newest first. Add one active candle that must be ignored.
    active = dict(rows[-1])
    active["datetime"] = "2026-09-21 23:59:00"
    return [active] + list(reversed(rows))


class BridgeSignalWorkerTests(unittest.TestCase):
    def test_normalize_drops_active_candle(self):
        values = make_values("up")
        rows = normalize_rows(values)
        self.assertEqual(len(rows), len(values) - 1)
        self.assertNotEqual(rows[-1]["datetime"], "2026-09-21 23:59:00")

    def test_strong_uptrend_produces_buy(self):
        signal = compute_signal(make_values("up"))
        self.assertEqual(signal["side"], "BUY")
        self.assertGreaterEqual(signal["score"], 6)
        self.assertLess(signal["sl"], signal["reference_close"])
        self.assertGreater(signal["tp"], signal["reference_close"])
        self.assertLessEqual(signal["risk_distance"], 1.60)

    def test_strong_downtrend_produces_sell(self):
        signal = compute_signal(make_values("down"))
        self.assertEqual(signal["side"], "SELL")
        self.assertGreaterEqual(signal["score"], 6)
        self.assertGreater(signal["sl"], signal["reference_close"])
        self.assertLess(signal["tp"], signal["reference_close"])
        self.assertLessEqual(signal["risk_distance"], 1.60)


if __name__ == "__main__":
    unittest.main()
