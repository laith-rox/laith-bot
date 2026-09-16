"""Side-by-side historical research for Laith Bot.

Usage:
  python v3_backtest.py candles.csv --spread 0.40 --slippage 0.10

The input candle CSV uses the same fields accepted by backtest.py.  This script
compares three variants under identical fill/cost assumptions:
- official_logic: current analyzer, including forced best-available bias,
- strict_logic: current analyzer but forced bias is WAIT,
- v3_global: strict setup + session + volatility + slow macro conflict veto.

The script is research only.  It never sends Telegram messages or broker orders.
"""
import argparse
import csv
from datetime import datetime, timedelta
import json
import math

from bot import entry_window
from engine import analyze, make_trade, advance_trade
from market import UTC, parse_bars, closed_only, DataError
from messages import LOCAL
from v3_global_data import GlobalContextProvider, build_snapshot, build_proxy_snapshot
from v3_metrics import summarize_r, block_bootstrap_mean_ci
from v3_research import analyze_v3


def _strict(decision):
    if decision.get("forced") or decision.get("reason") == "best_available_bias":
        return dict(decision, side="WAIT", reason="strict_forced_bias_rejected")
    return decision


def _macro_for(provider, now):
    if not provider or not provider.history:
        return None
    if getattr(provider, "source", None) == "twelve_proxy":
        return build_proxy_snapshot(provider.history, now)
    return build_snapshot(provider.history, now)


def simulate_variant(bars, analyzer, spread, slippage, macro_provider=None, news_events=None):
    if not all(math.isfinite(v) and v >= 0 for v in (spread, slippage)):
        raise ValueError("costs_must_be_finite_nonnegative")
    active = pending = None
    closed = []
    last_bar = None
    last_signal = 0.0
    day_r = {}

    for i, bar in enumerate(bars):
        if pending is not None and bar.start >= pending[1]:
            decision, expected_open = pending
            pending = None
            if bar.start == expected_open and min(decision["sl"], decision["tp1"]) < bar.open < max(decision["sl"], decision["tp1"]):
                active = make_trade(decision, bar.start)
                active.update(
                    status="active", announced=bar.start.timestamp(), entry=bar.open,
                    fill_model="first_full_bar_open_after_decision",
                    research_v3=decision.get("v3"),
                )
                last_signal = bar.start.timestamp()

        if active:
            active, _ = advance_trade(active, [bar])
            if active["status"] == "closed":
                active["gross_r"] = active.get("r")
                if active.get("r") is not None:
                    risk = abs(active["entry"] - active["initial_sl"])
                    active["r"] -= (spread + 2 * slippage) / risk
                day = bar.end.astimezone(LOCAL).date().isoformat()
                day_r[day] = day_r.get(day, 0.0) + (active["r"] if active.get("r") is not None else -1.0)
                closed.append(active)
                active = None

        now = bar.end + timedelta(seconds=15)
        if i < 1199 or active or pending or not entry_window(now):
            continue
        if now.timestamp() - last_signal < 3600:
            continue
        if day_r.get(now.astimezone(LOCAL).date().isoformat(), 0.0) <= -3.0:
            continue
        if news_events is not None and any(-900 <= event["time"] - now.timestamp() <= 1800 for event in news_events):
            continue

        try:
            macro = _macro_for(macro_provider, now)
            decision = analyzer(bars[max(0, i - 2399):i + 1], now, macro)
        except DataError:
            continue
        if decision.get("bar") == last_bar:
            continue
        last_bar = decision.get("bar")
        if decision.get("side") in ("BUY", "SELL"):
            pending = decision, bar.end + timedelta(minutes=5)

    values = [trade.get("r") for trade in closed if trade.get("r") is not None]
    result = summarize_r(values)
    result["closed"] = len(closed)
    result["open_at_end"] = int(active is not None)
    result["bootstrap_mean_r"] = block_bootstrap_mean_ci(values)
    result["by_session"] = {}
    result["by_volatility"] = {}
    for trade in closed:
        meta = trade.get("research_v3") or {}
        for bucket, key in ((result["by_session"], "session"), (result["by_volatility"], "volatility_regime")):
            label = meta.get(key, "UNLABELED")
            bucket.setdefault(label, []).append(trade.get("r"))
    result["by_session"] = {k: summarize_r(v) for k, v in result["by_session"].items()}
    result["by_volatility"] = {k: summarize_r(v) for k, v in result["by_volatility"].items()}
    return result


def official_analyzer(bars, now, macro):
    return analyze(bars, now)


def strict_analyzer(bars, now, macro):
    return _strict(analyze(bars, now))


def v3_analyzer(bars, now, macro):
    return analyze_v3(bars, now, macro=macro)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv")
    parser.add_argument("--spread", type=float, required=True)
    parser.add_argument("--slippage", type=float, required=True)
    parser.add_argument("--events-json")
    parser.add_argument("--skip-macro", action="store_true")
    args = parser.parse_args()

    with open(args.csv, newline="") as handle:
        payload = {"values": list(csv.DictReader(handle))}
    now = datetime.now(UTC)
    bars = closed_only(parse_bars(payload, now), now)

    events = None
    if args.events_json:
        with open(args.events_json) as handle:
            events = json.load(handle)

    provider = None
    if not args.skip_macro:
        provider = GlobalContextProvider()
        provider.refresh(now)

    variants = {
        "official_logic": official_analyzer,
        "strict_logic": strict_analyzer,
        "v3_global": v3_analyzer,
    }
    results = {
        name: simulate_variant(bars, analyzer, args.spread, args.slippage, provider, events)
        for name, analyzer in variants.items()
    }
    macro_label = "disabled"
    if provider:
        macro_label = ("Twelve market proxies, previous-day as-of context"
                       if provider.source == "twelve_proxy"
                       else "FRED previous-day as-of context")
    output = {
        "bars": len(bars),
        "first": bars[0].start.isoformat() if bars else None,
        "last": bars[-1].end.isoformat() if bars else None,
        "cost_assumptions": {"spread": args.spread, "slippage_each_side": args.slippage},
        "macro": macro_label,
        "variants": results,
        "warning": "historical and paper results do not establish future profitability",
    }
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
