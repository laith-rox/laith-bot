"""Forward-only historical evaluation with explicit execution cost assumptions.

    python backtest.py candles.csv --spread 0.40 --slippage 0.10

Cost numbers in this example are illustrative XAU price units, not measured fees.
Without an event file the report explicitly excludes historical news protection.
"""
import argparse
import csv
from datetime import datetime, timedelta
import json
import math

from bot import entry_window
from engine import analyze, make_trade, advance_trade
from market import UTC, parse_bars, closed_only, DataError, timestamp


def simulate(bars, spread, slippage, news_events=None, holdout_from=None):
    if not all(math.isfinite(x) and x >= 0 for x in (spread, slippage)):
        raise ValueError("costs_must_be_finite_nonnegative")
    if any(a.start >= b.start or a.minutes != 5 or b.minutes != 5 for a, b in zip(bars, bars[1:])):
        raise ValueError("backtest_requires_ordered_unique_five_minute_bars")
    closed, active, pending = [], None, None
    last_bar, last_signal = None, 0.0
    skipped_gaps = 0
    day_r = {}
    from messages import LOCAL
    for i, bar in enumerate(bars):
        # Decisions made after the previous close can only fill at a later bar's open.
        if pending is not None and bar.start >= pending[1]:
            decision, expected_open = pending
            pending = None
            if bar.start != expected_open or not min(decision["sl"], decision["tp1"]) < bar.open < max(decision["sl"], decision["tp1"]):
                skipped_gaps += 1
            else:
                active = make_trade(decision, bar.start)
                active.update(status="active", announced=bar.start.timestamp(), entry=bar.open,
                              fill_model="first_full_bar_open_after_decision")
                last_signal = bar.start.timestamp()
        if active:
            active, _ = advance_trade(active, [bar])
            if active["status"] == "closed":
                active["gross_r"] = active.get("r")
                if active.get("r") is not None:
                    risk = abs(active["entry"] - active["initial_sl"])
                    active["r"] -= (spread + 2 * slippage) / risk
                day = bar.end.astimezone(LOCAL).date().isoformat()
                day_r[day] = day_r.get(day, 0) + (active["gross_r"] if active["gross_r"] is not None else -1)
                closed.append(active)
                active = None
        now = bar.end + timedelta(seconds=15)
        if holdout_from and now < holdout_from:
            continue
        if i < 1199 or active or pending or not entry_window(now) or now.timestamp() - last_signal < 3600:
            continue
        if day_r.get(now.astimezone(LOCAL).date().isoformat(), 0) <= -3:
            continue
        if news_events is not None and any(-900 <= e["time"] - now.timestamp() <= 1800 for e in news_events):
            continue
        try:
            decision = analyze(bars[max(0, i-2399):i+1], now)
        except DataError:
            continue
        if decision.get("bar") == last_bar:
            continue
        last_bar = decision.get("bar")
        if decision["side"] in ("BUY", "SELL"):
            # The decision needs 15s after close, so the immediately opening bar is
            # already in progress. Wait for the following complete bar to avoid lookahead.
            pending = decision, bar.end + timedelta(minutes=5)
    measured = [t for t in closed if t.get("r") is not None]
    total = peak = max_drawdown = 0.0
    for trade in measured:
        total += trade["r"]
        peak = max(peak, total)
        max_drawdown = max(max_drawdown, peak - total)
    return {
        "bars": len(bars), "first": bars[0].start.isoformat() if bars else None,
        "last": bars[-1].end.isoformat() if bars else None,
        "holdout_from": holdout_from.isoformat() if holdout_from else None,
        "closed": len(closed), "measured": len(measured),
        "unresolved": len(closed)-len(measured), "open_at_end": int(active is not None),
        "pending_at_end": int(pending is not None), "skipped_gap_entries": skipped_gaps,
        "net_r": total, "max_drawdown_r": max_drawdown,
        "wins": sum(t["r"] > 0 for t in measured), "losses": sum(t["r"] < 0 for t in measured),
        "spread_price_units": spread, "slippage_each_side_price_units": slippage,
        "news_filter": "provided_events_only" if news_events is not None else "NOT_SIMULATED",
        "execution": "first_full_bar_after_decision; fixed_round_trip_cost; protection_from_next_bar",
        "limitations": ["historical_results_do_not_establish_future_profitability",
                        "costs_are_assumptions_not_broker_fills", "news_history_completeness_not_verified",
                        "live_network_latency_and_delivery_failures_not_simulated"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    parser.add_argument("--spread", type=float, required=True)
    parser.add_argument("--slippage", type=float, required=True)
    parser.add_argument("--events-json", help='JSON list of {"time": UTC epoch, "title": ...} high-impact USD events')
    parser.add_argument("--holdout-from", help="ISO date/time; earlier rows only warm up indicators")
    args = parser.parse_args()
    with open(args.csv, newline="") as handle:
        payload = {"values": list(csv.DictReader(handle))}
    now = datetime.now(UTC)
    bars = closed_only(parse_bars(payload, now), now)
    events = None
    if args.events_json:
        with open(args.events_json) as handle:
            events = json.load(handle)
        if not isinstance(events, list) or any(not isinstance(e.get("time"), (int, float)) for e in events):
            raise ValueError("invalid_news_event_file")
    result = simulate(bars, args.spread, args.slippage, events,
                      timestamp(args.holdout_from) if args.holdout_from else None)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
