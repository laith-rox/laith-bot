"""Independent Laith V4 paper-trading worker.

Isolation guarantees:
- separate SQLite database (/data/laith_v4.db by default),
- separate Railway project/service expected,
- no Telegram transport,
- no broker orders,
- no writes to Laith Bot or V3 databases,
- paper outcomes only.
"""
import argparse
from datetime import datetime, timezone
import json
import logging
import os
import time

from bot import entry_window
from engine import make_trade, advance_trade
from market import Market, DataError, require_fresh
from news import NewsGuard
from storage import Store
from v3_global_data import GlobalContextProvider
from v3_metrics import summarize_r
from v4_experiment import experiment_record
from v4_research import analyze_v4

UTC = timezone.utc
LOG = logging.getLogger("laith.v4")


class V4Paper:
    def __init__(self, store, market, news, global_context=None, cooldown_minutes=60):
        self.store = store
        self.market = market
        self.news = news
        self.global_context = global_context or GlobalContextProvider()
        self.cooldown = cooldown_minutes * 60
        self.experiment = experiment_record()
        self.store.db.execute(
            "CREATE TABLE IF NOT EXISTS v4_paper(id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        self.store.db.commit()
        self.store.set("v4_experiment", self.experiment)

    def _paper_rows(self):
        rows = self.store.db.execute("SELECT data FROM v4_paper ORDER BY rowid").fetchall()
        return [json.loads(row[0]) for row in rows]

    def _update_stats(self):
        trades = self._paper_rows()
        matching = [t for t in trades if t.get("experiment_id") == self.experiment["id"]]
        stats = summarize_r([trade.get("r") for trade in matching])
        stats["experiment_id"] = self.experiment["id"]
        stats["all_saved_trades"] = len(trades)
        stats["matching_experiment_trades"] = len(matching)
        buckets = {
            "by_session": ("session",),
            "by_volatility": ("volatility_regime",),
            "by_macro": ("macro_alignment",),
            "by_breakout": ("breakout_state",),
            "by_correction_strength": ("correction", "strength"),
        }
        collected = {name: {} for name in buckets}
        for trade in matching:
            research = trade.get("research_v4") or {}
            for bucket_name, path in buckets.items():
                value = research
                for key in path:
                    value = value.get(key) if isinstance(value, dict) else None
                label = value or "UNKNOWN"
                collected[bucket_name].setdefault(label, []).append(trade.get("r"))
        for bucket_name, values in collected.items():
            stats[bucket_name] = {k: summarize_r(v) for k, v in sorted(values.items())}
        self.store.set("v4_stats", stats)
        return stats

    def _finish(self, trade):
        with self.store.db:
            self.store.db.execute(
                "INSERT OR IGNORE INTO v4_paper(id,data) VALUES (?,?)",
                (trade["id"], json.dumps(trade, allow_nan=False)),
            )
        stats = self._update_stats()
        self.store.set("v4_active", None)
        LOG.info(
            "paper_closed experiment=%s id=%s outcome=%s r=%s measured=%s net_r=%.3f max_dd=%.3f",
            self.experiment["id"], trade["id"], trade.get("outcome"), trade.get("r"),
            stats.get("measured"), stats.get("net_r", 0.0), stats.get("max_drawdown_r", 0.0),
        )

    def cycle(self, now):
        bars = self.market.fetch(now)
        active = self.store.get("v4_active")
        if active:
            active, _ = advance_trade(active, bars)
            if active["status"] == "closed":
                self._finish(active)
                active = None
            else:
                self.store.set("v4_active", active)

        try:
            macro = self.global_context.snapshot(now)
            self.store.set("v4_macro", macro)
            self.store.set("v4_macro_error", self.global_context.last_error)
            if self.global_context.last_error:
                LOG.warning("macro_context_partial error=%s", self.global_context.last_error)
        except Exception as exc:
            macro = None
            detail = type(exc).__name__ + ":" + str(exc)
            self.store.set("v4_macro_error", detail)
            LOG.warning("macro_context_unavailable error=%s", detail)

        decision = analyze_v4(bars, now, macro=macro)
        self.store.set("v4_last_analysis", decision)
        self.store.set("v4_heartbeat", now.timestamp())

        allowed_news, news_reason, nearby = self.news.check(now)
        research = decision.get("v4", {})
        support = research.get("nearest_support") or {}
        resistance = research.get("nearest_resistance") or {}
        correction = research.get("correction") or {}
        risk = research.get("structural_risk") or {}
        self.store.set("v4_last_structure", {
            "time": now.isoformat(),
            "side": decision.get("side"),
            "reason": decision.get("reason"),
            "support": support,
            "resistance": resistance,
            "breakout_state": research.get("breakout_state"),
            "critical_level": research.get("critical_level"),
            "correction": correction,
            "risk": risk,
        })
        LOG.info(
            "analysis experiment=%s side=%s reason=%s session=%s vol=%s pct=%s macro=%s macro_score=%s coverage=%s news=%s",
            self.experiment["id"], decision.get("side"), decision.get("reason"),
            research.get("session"), research.get("volatility_regime"),
            research.get("volatility_percentile"), research.get("macro_alignment"),
            research.get("macro_score"), macro.get("coverage") if macro else None, news_reason,
        )
        LOG.info(
            "structure support=%s resistance=%s break=%s corr_dir=%s corr_strength=%s corr_triggered=%s corr_start=%s corr_t1=%s corr_t2=%s stop=%s room_r=%s",
            support.get("center"), resistance.get("center"), research.get("breakout_state"),
            correction.get("direction"), correction.get("strength"), correction.get("triggered"),
            correction.get("start_zone"), correction.get("target1"), correction.get("target2"),
            risk.get("stop"), risk.get("room_r"),
        )

        if active or decision.get("side") not in ("BUY", "SELL"):
            return
        if not entry_window(now) or not allowed_news or nearby:
            return
        if now.timestamp() - self.store.get("v4_last_entry", 0) < self.cooldown:
            return

        require_fresh(bars, now, 120)
        quote = self.market.quote(lambda: datetime.now(UTC))
        now2 = datetime.now(UTC)
        require_fresh(bars, now2, 120)
        tolerance = min(1.0, decision["atr"] * 0.25)
        shift = quote["price"] - decision["price"]
        if abs(shift) > tolerance:
            self.store.set("v4_last_block", "market_price_moved")
            return

        adjusted = dict(decision)
        for field in ("price", "sl", "tp1", "tp2"):
            adjusted[field] += shift
        trade = make_trade(adjusted, now2)
        trade.update(
            status="active",
            announced=now2.timestamp(),
            last_end=None,
            quote_time=quote["time"],
            quote_source=quote["source"],
            research_v4=research,
            macro_snapshot=macro,
            experiment_id=self.experiment["id"],
            paper_only=True,
            generation="V4",
        )
        self.store.set("v4_active", trade)
        self.store.set("v4_last_entry", now2.timestamp())
        LOG.info(
            "paper_open experiment=%s id=%s side=%s entry=%.2f sl=%.2f tp1=%.2f tp2=%.2f session=%s vol=%s macro=%s",
            self.experiment["id"], trade["id"], trade["side"], trade["entry"], trade["stop"],
            trade["tp1"], trade["tp2"], research.get("session"), research.get("volatility_regime"),
            research.get("macro_alignment"),
        )


def run(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(args.db)
    market = Market(args.twelve_key)
    news = NewsGuard(store)
    global_context = GlobalContextProvider(refresh_seconds=args.macro_refresh, twelve_key=args.twelve_key)
    paper = V4Paper(store, market, news, global_context, args.cooldown)
    LOG.info("starting independent V4 paper worker db=%s experiment=%s", args.db, paper.experiment["id"])
    try:
        while True:
            now = datetime.now(UTC)
            try:
                paper.cycle(now)
                store.set("v4_last_error", None)
            except DataError as exc:
                store.set("v4_last_error", str(exc))
                LOG.warning("cycle_data_error reason=%s", exc)
            except Exception:
                LOG.exception("cycle_failed")
            time.sleep(args.interval)
    finally:
        store.close()


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.getenv("V4_DB_PATH", "/data/laith_v4.db"))
    p.add_argument("--twelve-key", default=os.getenv("TWELVE_DATA_API_KEY"))
    p.add_argument("--interval", type=int, default=int(os.getenv("V4_CHECK_INTERVAL_SECONDS", "900")))
    p.add_argument("--cooldown", type=int, default=int(os.getenv("V4_SIGNAL_COOLDOWN_MINUTES", "60")))
    p.add_argument("--macro-refresh", type=int, default=int(os.getenv("V4_MACRO_REFRESH_SECONDS", "21600")))
    return p


if __name__ == "__main__":
    run(parser().parse_args())
