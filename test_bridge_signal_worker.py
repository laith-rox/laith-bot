import unittest
from unittest.mock import patch
import bridge_signal_worker as worker

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


def with_latest(values, *, open_, high, low, close):
    values = [dict(row) for row in values]
    # values[0] is active; values[1] is the latest closed candle.
    values[1].update(open=f"{open_:.2f}", high=f"{high:.2f}",
                     low=f"{low:.2f}", close=f"{close:.2f}")
    return values


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

    def test_first_break_above_resistance_is_not_chased(self):
        values = make_values("up")
        base = float(values[8]["close"])
        # Six closed candles form a horizontal resistance; only the latest
        # candle pokes above it, so there is no one-bar hold confirmation yet.
        for i in range(2, 9):
            values[i].update(open=f"{base:.2f}", high=f"{base+0.30:.2f}",
                             low=f"{base-0.30:.2f}", close=f"{base:.2f}")
        values = with_latest(values, open_=base, high=base+1.35,
                             low=base-0.10, close=base+1.05)
        signal = compute_signal(values)
        self.assertIsNone(signal["side"])
        self.assertEqual(signal["reason"], "resistance_not_confirmed")

    def test_sell_pullback_inside_larger_uptrend_is_blocked(self):
        values = make_values("up")
        previous = float(values[2]["close"])
        values = with_latest(values, open_=previous+0.25, high=previous+0.35,
                             low=previous-2.20, close=previous-2.00)
        signal = compute_signal(values)
        if signal["sell_score"] >= 5:
            self.assertIsNone(signal["side"])
            self.assertEqual(signal["reason"], "sell_is_correction_in_uptrend")



class StopWorker(BaseException):
    pass


class PublishLimitTests(unittest.TestCase):
    def run_worker(self, cap, health, iterations=14):
        health = {"mode": "DEMO", **health}
        signals = [
            {"bar": str(i), "side": "BUY", "score": 6,
             "reference_close": 4300.0, "risk_distance": 1.2}
            for i in range(iterations)
        ]
        with patch.multiple(worker, BRIDGE_URL="https://example.invalid",
                            BRIDGE_PUBLISH_TOKEN="test-only",
                            MAX_PUBLISH_PER_HOUR=cap,
                            ALLOW_STALE_MT5_STATE=False), \
             patch.object(worker, "bridge_health", return_value=health), \
             patch.object(worker, "fetch_market_values", return_value=[]), \
             patch.object(worker, "compute_signal", side_effect=signals), \
             patch.object(worker, "publish_signal",
                          return_value=(201, {"ok": True}, "test")) as publish, \
             patch.object(worker.time, "time", return_value=1000.0), \
             patch.object(worker.time, "sleep",
                          side_effect=[None] * (iterations - 1) + [StopWorker()]), \
             patch("builtins.print"):
            with self.assertRaises(StopWorker):
                worker.run_forever()
            return publish.call_count

    def test_zero_allows_more_than_twelve_signals_without_hourly_wait(self):
        self.assertEqual(self.run_worker(0, {
            "enabled": True, "client_state_fresh": True,
            "position_open": False, "pending": 0}), 14)

    def test_positive_cap_still_limits_publishing(self):
        self.assertEqual(self.run_worker(2, {
            "enabled": True, "client_state_fresh": True,
            "position_open": False, "pending": 0}), 2)

    def test_unlimited_does_not_bypass_execution_state_checks(self):
        for changes in ({"enabled": False}, {"client_state_fresh": False},
                        {"position_open": True}, {"pending": 1}):
            health = {"enabled": True, "client_state_fresh": True,
                      "position_open": False, "pending": 0}
            health.update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(self.run_worker(0, health), 0)

    def test_negative_cap_is_configuration_error(self):
        with patch.object(worker, "MAX_PUBLISH_PER_HOUR", -1):
            with self.assertRaisesRegex(RuntimeError, "invalid_max_publish_per_hour"):
                worker.validate_config()


class LegacyCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.health = {"mode": "DEMO", "enabled": True,
                       "client_state_fresh": False, "client_last_seen_age": None,
                       "client_poll_fresh": True, "position_open": False, "pending": 0}

    def test_legacy_polling_requires_explicit_compatibility(self):
        with patch.object(worker, "ALLOW_STALE_MT5_STATE", False):
            self.assertEqual(worker.execution_block_reason(self.health), "mt5_state_stale")
        with patch.object(worker, "ALLOW_STALE_MT5_STATE", True):
            self.assertIsNone(worker.execution_block_reason(self.health))

    def test_compatibility_never_accepts_disconnected_or_stale_reporting_clients(self):
        with patch.object(worker, "ALLOW_STALE_MT5_STATE", True):
            for changes, reason in [
                ({"client_poll_fresh": False}, "mt5_disconnected"),
                ({"client_last_seen_age": 11}, "mt5_state_stale"),
                ({"mode": "LIVE"}, "bridge_not_demo"),
                ({"enabled": False}, "bridge_disabled"),
                ({"pending": 1}, "position_or_pending"),
                ({"position_open": True}, "position_or_pending"),
            ]:
                with self.subTest(changes=changes):
                    self.assertEqual(worker.execution_block_reason({**self.health, **changes}), reason)


if __name__ == "__main__":
    unittest.main()
