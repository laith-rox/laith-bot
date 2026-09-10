import copy
from datetime import datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from bot import App, daily_risk_blocked, entry_window
from engine import analyze, make_trade, advance_trade, rsi, ema
from market import Bar, DataError, parse_bars, closed_only, resample, require_fresh, Market
from news import NewsGuard, parse_calendar
from storage import Store
from transport import Telegram, SecretFilter, dispatch
from backtest import simulate

UTC = timezone.utc
NOW = datetime(2026, 9, 10, 12, 0, 15, tzinfo=UTC)


def history(monotonic=False):
    start = NOW.replace(second=0) - timedelta(minutes=2400 * 5)
    result = []
    previous = 1999.35
    for i in range(800):
        target = 2000 + i * 0.15 + (0 if monotonic else (0.65 if i % 2 else -0.65))
        opening = previous
        for j in range(3):
            closing = previous + (target - previous) * (j + 1) / 3
            result.append(Bar(start + timedelta(minutes=5*(3*i+j)), opening,
                              max(opening, closing)+0.4, min(opening, closing)-0.4, closing))
            opening = closing
        previous = target
    return result


def active_trade(side="BUY"):
    d = 1 if side == "BUY" else -1
    decision = {"side": side, "price": 100.0, "sl": 100-10*d, "tp1": 100+18*d,
                "tp2": 100+26*d, "bar": "2026-09-10T12:00:00+00:00"}
    trade = make_trade(decision, NOW)
    trade.update(status="active", announced=NOW.replace(second=0).timestamp())
    return trade


def candle(o=100, h=105, l=95, c=101, offset=0):
    return Bar(NOW.replace(second=0)+timedelta(minutes=offset), o, h, l, c)


def response(data, status=200):
    return Mock(status_code=status, json=Mock(return_value=data))


class MarketTests(unittest.TestCase):
    def payload(self, **changes):
        row = {"datetime": "2026-09-10 11:55:00", "open": "100", "high": "102", "low": "99", "close": "101"}
        row.update(changes)
        return {"meta": {"symbol": "XAU/USD"}, "values": [row]}

    def test_current_candle_excluded(self):
        bars = parse_bars(self.payload(datetime="2026-09-10 12:00:00"), NOW)
        self.assertEqual(closed_only(bars, NOW), [])

    def test_future_timestamp_rejected(self):
        with self.assertRaises(DataError):
            parse_bars(self.payload(datetime="2026-09-10 13:00:00"), NOW)

    def test_nonfinite_invalid_and_negative_ohlc_rejected(self):
        for changes in ({"close": "nan"}, {"high": "inf"}, {"high": "98"}, {"low": "-1"}):
            with self.subTest(changes=changes), self.assertRaises(DataError):
                parse_bars(self.payload(**changes), NOW)

    def test_timezone_normalized_and_duplicates_checked(self):
        payload = self.payload(datetime="2026-09-10T14:55:00+03:00")
        payload["values"] *= 2
        bars = parse_bars(payload, NOW)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].start.hour, 11)
        payload["values"] = [payload["values"][0], dict(payload["values"][0], close="100")]
        with self.assertRaises(DataError):
            parse_bars(payload, NOW)

    def test_clock_hour_alignment_and_missing_bar(self):
        bars = history()
        hours = resample(bars[1:], 60)
        self.assertEqual(len(hours), 199)
        self.assertTrue(all(b.start.minute == 0 for b in hours))
        with_gap = bars[:6] + bars[7:]
        self.assertEqual(len(resample(with_gap, 60)), 199)

    def test_short_incomplete_group_not_emitted(self):
        self.assertEqual(resample(history()[:2], 15), [])

    def test_stale_closed_data_rejected(self):
        with self.assertRaises(DataError):
            require_fresh(history()[:-3], NOW, 600)

    def test_provider_quota_failure_has_no_secret(self):
        session = Mock()
        session.get.return_value = response({"status": "error", "code": 429, "message": "api_key=private"})
        with self.assertRaisesRegex(DataError, "market_quota_reached"):
            Market("secret", session).fetch(NOW)
        self.assertEqual(session.get.call_args.kwargs["params"]["timezone"], "UTC")


class StrategyTests(unittest.TestCase):
    def test_known_ema_values(self):
        self.assertEqual(ema([1, 2, 3, 4], 3), [1, 1.5, 2.25, 3.125])

    def test_wilder_rsi_reference(self):
        values = [44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,
                  45.84,46.08,45.89,46.03,45.61,46.28,46.28]
        self.assertAlmostEqual(rsi(values), 70.464135, places=5)
        self.assertEqual(rsi([100]*20), 50)

    def test_rsi_extreme_cannot_be_outvoted(self):
        decision = analyze(history(monotonic=True), NOW)
        self.assertEqual(decision["rsi"], 100)
        self.assertEqual(decision["side"], "WAIT")

    def test_valid_signal_has_consistent_levels(self):
        d = analyze(history(), NOW)
        self.assertEqual(d["side"], "BUY")
        self.assertLess(d["sl"], d["price"])
        self.assertLess(d["price"], d["tp1"])
        self.assertLess(d["tp1"], d["tp2"])
        self.assertAlmostEqual((d["tp2"]-d["price"])/(d["price"]-d["sl"]), 2.6/1.4)

    def test_future_bars_do_not_change_prior_resampling(self):
        bars = history()
        at = bars[-7].end + timedelta(seconds=15)
        before = resample(closed_only(bars, at), 15)
        after = resample(closed_only(bars + [candle(h=999, c=500)], at), 15)
        self.assertEqual(before, after)

    def test_weekend_and_palestine_schedule(self):
        self.assertTrue(entry_window(NOW))
        self.assertFalse(entry_window(NOW + timedelta(days=2)))
        self.assertFalse(entry_window(NOW.replace(hour=0)))


class LifecycleTests(unittest.TestCase):
    def test_long_and_short_stop(self):
        for side, bar in (("BUY", candle(l=89)), ("SELL", candle(h=111))):
            trade, events = advance_trade(active_trade(side), [bar])
            self.assertEqual(trade["outcome"], "STOP")
            self.assertAlmostEqual(trade["r"], -1)

    def test_long_and_short_final_target(self):
        for side, bar in (("BUY", candle(h=127,c=125)), ("SELL", candle(l=73,c=75))):
            trade, _ = advance_trade(active_trade(side), [bar])
            self.assertEqual(trade["outcome"], "TP2")
            self.assertAlmostEqual(trade["r"], 2.6)

    def test_same_bar_stop_target_unresolved(self):
        trade, _ = advance_trade(active_trade(), [candle(h=127,l=89)])
        self.assertEqual(trade["outcome"], "AMBIGUOUS")
        self.assertIsNone(trade["r"])

    def test_target_one_stop_activates_next_bar_only(self):
        trade, events = advance_trade(active_trade(), [candle(h=120,l=95,c=115)])
        self.assertEqual(trade["status"], "active")
        self.assertEqual(trade["stop"], 100)
        self.assertEqual([e["kind"] for e in events], ["tp1"])
        trade, _ = advance_trade(trade, [candle(o=115,h=117,l=99,c=102,offset=5)])
        self.assertEqual(trade["outcome"], "PROTECTED_STOP")
        self.assertEqual(trade["r"], 0)

    def test_gap_stop_uses_worse_open(self):
        trade, _ = advance_trade(active_trade(), [candle(o=80,h=88,l=79,c=85)])
        self.assertEqual(trade["r"], -2)

    def test_pre_delivery_extremes_not_used(self):
        original = active_trade()
        original["announced"] += 15
        trade, events = advance_trade(original, [candle(h=140,l=80,c=101)])
        self.assertEqual(trade["status"], "active")
        self.assertEqual(events, [])

    def test_replay_is_idempotent(self):
        bar = candle(h=120,c=115)
        trade, _ = advance_trade(active_trade(), [bar])
        replay, events = advance_trade(trade, [bar])
        self.assertEqual(replay, trade)
        self.assertEqual(events, [])

    def test_data_gap_excludes_performance(self):
        trade, _ = advance_trade(active_trade(), [candle(), candle(h=130,offset=15)])
        self.assertTrue(trade["data_gap"])
        self.assertIsNone(trade["r"])


class StatefulTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def pending(self):
        trade = active_trade()
        trade.update(status="pending", announced=None)
        self.store.prepare_entry(trade, "test", NOW.timestamp())
        return trade

    def test_delivery_retry_then_confirmation_then_restart(self):
        self.pending()
        session = Mock()
        session.post.side_effect = [response({"ok":False,"error_code":503}, 503),
            response({"ok":True,"result":{"message_id":7,"chat":{"id":1}}})]
        telegram = Telegram("offline", "1", session)
        dispatch(self.store, telegram, lambda: NOW.timestamp())
        self.assertIsNone(self.store.get("last_signal_at"))
        dispatch(self.store, telegram, lambda: NOW.timestamp()+5)
        self.assertEqual(self.store.get("last_signal_at"), NOW.timestamp()+5)
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.active()["message_id"], 7)
        self.assertFalse(self.store.prepare_entry(active_trade("SELL"), "test", NOW.timestamp()+6))

    def test_read_timeout_not_blindly_retried(self):
        self.pending()
        session = Mock()
        session.post.side_effect = requests.ReadTimeout("token=do-not-print")
        dispatch(self.store, Telegram("offline", "1", session), lambda: NOW.timestamp())
        dispatch(self.store, Telegram("offline", "1", session), lambda: NOW.timestamp()+30)
        self.assertEqual(session.post.call_count, 1)
        self.assertTrue(self.store.get("paused"))
        self.assertEqual(self.store.active()["status"], "uncertain_delivery")

    def test_crash_during_send_requires_review(self):
        self.pending()
        self.store.claim(NOW.timestamp())
        self.store.close()
        self.store = Store(self.path)
        self.store.recover_inflight(NOW.timestamp()+30)
        self.assertEqual(self.store.active()["status"], "uncertain_delivery")
        self.assertTrue(self.store.get("paused"))
        self.assertIsNone(self.store.claim(NOW.timestamp()+60))

    def test_expired_entry_released_without_cooldown(self):
        self.pending()
        self.assertIsNone(self.store.claim(NOW.timestamp()+121))
        self.assertIsNone(self.store.active())
        self.assertIsNone(self.store.get("last_signal_at"))

    def test_pause_cancels_unsent_entry(self):
        self.pending()
        self.store.pause(True)
        self.assertIsNone(self.store.active())
        self.assertIsNone(self.store.claim(NOW.timestamp()))

    def test_success_requires_valid_recipient_ack(self):
        session = Mock()
        session.post.return_value = response({"ok":True,"result":{"message_id":7,"chat":{"id":2}}})
        self.assertEqual(Telegram("offline", "1", session).send("test").status, "uncertain")

    def test_429_respects_retry_after(self):
        self.pending()
        session = Mock()
        session.post.return_value = response({"ok":False,"error_code":429,"parameters":{"retry_after":90}}, 429)
        dispatch(self.store, Telegram("offline", "1", session), lambda: NOW.timestamp())
        self.assertIsNone(self.store.claim(NOW.timestamp()+60))
        self.assertIsNotNone(self.store.claim(NOW.timestamp()+90))

    def test_unknown_outcome_not_counted_as_win(self):
        trade, _ = advance_trade(active_trade(), [candle(h=130,l=80)])
        self.store.save_transition(trade, [], NOW.timestamp())
        self.assertEqual(self.store.stats()["wins"], 0)
        self.assertEqual(self.store.stats()["unresolved"], 1)

    def test_daily_risk_brake(self):
        for i in range(3):
            trade, _ = advance_trade(active_trade(), [candle(l=89)])
            trade["id"] += str(i)
            self.store.save_transition(trade, [], NOW.timestamp())
        self.assertTrue(daily_risk_blocked(self.store, NOW))
        self.assertFalse(daily_risk_blocked(self.store, NOW+timedelta(days=1)))

    def test_end_to_end_news_blocks_entry_but_not_existing_stop(self):
        market, news, telegram = Mock(), Mock(), Mock()
        market.fetch.return_value = history()
        news.check.return_value = False, "news_blackout", []
        app = App(self.store, market, telegram, news)
        app.cycle(NOW)
        self.assertIsNone(self.store.active())
        self.assertEqual(self.store.get("last_analysis")["reason"], "news_blackout")
        trade = active_trade()
        trade["announced"] = history()[-1].start.timestamp()
        self.store.save_transition(trade, [], NOW.timestamp())
        self.store.pause(True)
        app.cycle(NOW)
        self.assertIsNone(self.store.active())
        self.assertEqual(self.store.trade(trade["id"])["status"], "closed")

    def test_end_to_end_entry_once_and_confirmed_delivery(self):
        market, news = Mock(), Mock()
        market.fetch.return_value = history()
        news.check.return_value = True, "calendar_clear", []
        session = Mock()
        session.post.return_value = response({"ok":True,"result":{"message_id":9,"chat":{"id":1}}})
        telegram = Telegram("offline", "1", session)
        app = App(self.store, market, telegram, news)
        app.cycle(NOW)
        self.assertEqual(self.store.active()["status"], "pending")
        dispatch(self.store, telegram, lambda: NOW.timestamp()+1)
        self.assertEqual(self.store.active()["status"], "active")
        app.cycle(NOW)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM signals").fetchone()[0], 1)

    def test_commands_require_owner_private_chat(self):
        telegram = Mock(chat_id="1")
        telegram.read.return_value = [{"update_id":1,"message":{"date":int(NOW.timestamp()),
            "chat":{"id":2,"type":"private"},"from":{"id":2},"text":"/pause"}}]
        app = App(self.store, Mock(), telegram, Mock())
        app.commands(NOW)
        self.assertFalse(self.store.get("paused", False))
        telegram.read.return_value = [{"update_id":2,"message":{"date":int(NOW.timestamp()),
            "chat":{"id":1,"type":"private"},"from":{"id":1},"text":"/pause"}}]
        app.commands(NOW)
        self.assertTrue(self.store.get("paused"))


class BacktestTests(unittest.TestCase):
    def test_costs_and_coverage_are_explicit(self):
        result = simulate(history(), 0.4, 0.1)
        self.assertEqual(result["news_filter"], "NOT_SIMULATED")
        self.assertEqual(result["spread_price_units"], 0.4)

    def test_higher_cost_cannot_improve_same_sample(self):
        cheap = simulate(history(), 0, 0)
        costly = simulate(history(), 1, 0.2)
        self.assertGreater(cheap["measured"], 0)
        self.assertEqual(cheap["closed"], costly["closed"])
        self.assertLessEqual(costly["net_r"], cheap["net_r"])

    def test_no_holdout_trades_before_boundary(self):
        result = simulate(history(), 0, 0, holdout_from=NOW+timedelta(days=1))
        self.assertEqual(result["closed"], 0)
        self.assertEqual(result["open_at_end"], 0)

    def test_bad_costs_rejected(self):
        for cost in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                simulate(history(), cost, 0)

    def test_historical_fill_occurs_after_decision_time(self):
        decision_times, fill_times = [], []

        def decision(bars, now):
            decision_times.append(now)
            p = bars[-1].close
            return {"side":"BUY", "price":p, "sl":p-10, "tp1":p+20, "tp2":p+30,
                    "bar":bars[-1].end.isoformat()}

        def track(trade, bars):
            fill_times.append(trade["announced"])
            return advance_trade(trade, bars)

        with patch("backtest.analyze", side_effect=decision), patch("backtest.entry_window", return_value=True), \
                patch("backtest.advance_trade", side_effect=track):
            simulate(history()[:1204], 0, 0)
        self.assertTrue(fill_times)
        self.assertGreater(fill_times[0], decision_times[0].timestamp())


class NewsAndLoggingTests(unittest.TestCase):
    def test_calendar_requires_current_week(self):
        payload = [{"title":"CPI", "country":"USD", "impact":"High", "date":"2026-09-11T08:30:00-04:00"}]
        self.assertEqual(len(parse_calendar(payload, NOW)), 1)
        with self.assertRaises(ValueError):
            parse_calendar(payload, NOW+timedelta(days=7))

    def test_calendar_failure_blocks_new_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"db")
            session = Mock()
            session.get.side_effect = requests.ConnectTimeout()
            self.assertFalse(NewsGuard(store, session).check(NOW)[0])
            store.close()

    def test_news_blackout_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"db")
            session = Mock()
            session.get.return_value = response([{"title":"PPI","country":"USD","impact":"High",
                                                   "date":"2026-09-10T08:30:00-04:00"}])
            guard = NewsGuard(store, session)
            self.assertFalse(guard.check(NOW)[0])
            self.assertTrue(guard.check(NOW+timedelta(minutes=46))[0])
            store.close()

    def test_secret_filter_suppresses_values_and_tracebacks(self):
        record = logging.LogRecord("test", logging.ERROR, "x", 1,
            "URL apikey=private&x=1 token=other", (), (RuntimeError, RuntimeError("secret"), None))
        SecretFilter(("private", "other")).filter(record)
        self.assertNotIn("private", record.msg)
        self.assertNotIn("other", record.msg)
        self.assertIsNone(record.exc_info)


if __name__ == "__main__":
    unittest.main()
