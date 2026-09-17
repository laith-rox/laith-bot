from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from market import Bar
from storage import Store
from v4_h4 import analyze_h4, make_h4_trade, process_h4, resample_h4

UTC = timezone.utc


class Outcome:
    status = "sent"
    message_id = 1
    error = None


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


def bullish_h4(count=50, start=None):
    start = start or datetime(2026, 9, 1, tzinfo=UTC)
    bars = []
    close = 4000.0
    for index in range(count):
        previous = close
        close += 2.0 if index % 2 == 1 else -1.0
        if index == count - 1:
            close = previous + 2.0
        opening = previous
        high = max(opening, close) + 1.0
        low = min(opening, close) - 1.0
        bars.append(Bar(start + timedelta(hours=4 * index), opening, high, low, close, 240))
    return bars


def five_minute_from_h4(h4_bars):
    result = []
    for candle in h4_bars:
        step = (candle.close - candle.open) / 48.0
        current = candle.open
        for index in range(48):
            nxt = candle.close if index == 47 else current + step
            high = max(current, nxt) + 0.05
            low = min(current, nxt) - 0.05
            result.append(Bar(candle.start + timedelta(minutes=5 * index), current, high, low, nxt, 5))
            current = nxt
    return result


class V4H4Tests(unittest.TestCase):
    def test_resample_builds_closed_four_hour_candle(self):
        start = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
        bars = []
        for index in range(48):
            price = 4300 + index * 0.1
            bars.append(Bar(start + timedelta(minutes=5 * index), price, price + 0.2, price - 0.2, price + 0.1, 5))
        h4 = resample_h4(bars, start + timedelta(hours=4, minutes=1))
        self.assertEqual(len(h4), 1)
        self.assertEqual(h4[0].minutes, 240)
        self.assertEqual(h4[0].start, start)

    def test_current_partial_h4_is_not_used(self):
        start = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
        bars = [
            Bar(start + timedelta(minutes=5 * index), 4300, 4301, 4299, 4300.5, 5)
            for index in range(40)
        ]
        h4 = resample_h4(bars, start + timedelta(hours=3, minutes=30))
        self.assertEqual(h4, [])

    def test_bullish_h4_can_build_independent_buy(self):
        decision = analyze_h4(bullish_h4())
        self.assertEqual(decision["side"], "BUY")
        self.assertGreaterEqual(decision["buy"], 5)
        self.assertGreater(decision["buy"], decision["sell"])
        self.assertIsNotNone(decision["sl"])
        self.assertIsNotNone(decision["tp1"])
        self.assertIsNotNone(decision["tp2"])

    def test_h4_trade_has_wider_two_target_lifecycle(self):
        decision = analyze_h4(bullish_h4())
        now = datetime(2026, 9, 10, 12, 1, tzinfo=UTC)
        trade = make_h4_trade(decision, now, decision["price"])
        risk = trade["entry"] - trade["stop"]
        self.assertEqual(trade["kind"], "H4")
        self.assertTrue(trade["paper_only"])
        self.assertAlmostEqual((trade["tp1"] - trade["entry"]) / risk, 1.4, places=6)
        self.assertAlmostEqual((trade["tp2"] - trade["entry"]) / risk, 2.2, places=6)

    def test_process_h4_evaluates_once_per_closed_h4_bar(self):
        candles = bullish_h4(50)
        bars = five_minute_from_h4(candles)
        now = candles[-1].end + timedelta(minutes=1)
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "db.sqlite")
        notifier = FakeNotifier()
        try:
            first = process_h4(store, notifier, bars, now)
            self.assertTrue(any(event["kind"] == "open" for event in first))
            self.assertIsNotNone(store.get("v4_h4_active"))
            sent = len(notifier.messages)
            second = process_h4(store, notifier, bars, now + timedelta(minutes=1))
            self.assertEqual(second, [])
            self.assertEqual(len(notifier.messages), sent)
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
