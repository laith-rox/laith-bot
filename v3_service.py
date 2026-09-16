"""Standalone V3 paper-trading worker.

Safe isolation rules:
- separate SQLite database by default (/data/laith_v3.db),
- no Telegram transport,
- no broker orders,
- no writes to the live bot database,
- research/v3-signal-lab branch only until explicitly promoted.

The worker combines the existing XAU/USD market feed with slow-moving public
macro context from v3_global_data.py.  It records paper outcomes only.
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
from v3_experiment import experiment_record
from v3_global_data import GlobalContextProvider
from v3_metrics import summarize_r
from v3_research import analyze_v3

UTC = timezone.utc
LOG = logging.getLogger("laith.v3")


class V3Paper:
    def __init__(self, store, market, news, global_context=None, cooldown_minutes=60):
        self.store = store
        self.market = market
        self.news = news
        self.global_context = global_context or GlobalContextProvider()
        self.cooldown = cooldown_minutes * 60
        self.experiment = experiment_record()
        self.store.db.execute(
            "CREATE TABLE IF NOT EXISTS v3_paper(id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        self.store.db.commit()
        self.store.set("v3_experiment", self.experiment)

    def _paper_rows(self):
        rows = self.store.db.execute("SELECT data FROM v3_paper ORDER BY rowid").fetchall()
        return [json.loads(row[0]) for row in rows]

    def _update_stats(self):
        trades = self._paper_rows()
        matching = [t for t in trades if t.get("experiment_id") == self.experiment["id"]]
        stats = summarize_r([trade.get("r") for trade in matching])
        stats["experiment_id"] = self.experiment["id"]
        stats["all_saved_trades"] = len(trades)
        stats["matching_experiment_trades"] = len(matching)
        by_session, by_vol, by_macro = {}, {}, {}
        for trade in matching:
            research = trade.get("research_v3") or {}
            for target, label in (
                (by_session, research.get("session", "UNKNOWN")),
                (by_vol, research.get("volatility_regime", "UNKNOWN")),
                (by_macro, research.get("macro_alignment", "UNKNOWN")),
            ):
                target.setdefault(label, []).append(trade.get("r"))
        stats["by_session"] = {k: summarize_r(v) for k, v in sorted(by_session.items())}
        stats["by_volatility"] = {k: summarize_r(v) for k, v in sorted(by_vol.items())}
        stats["by_macro"] = {k: summarize_r(v) for k, v in sorted(by_macro.items())}
        self.store.set("v3_stats", stats)
        return stats

    def _finish(self, trade):
        with self.store.db:
            self.store.db.execute(
                "INSERT OR IGNORE INTO v3_paper(id,data) VALUES (?,?)",
                (trade["id"], json.dumps(trade, allow_nan=False)),
            )
        stats = self._update_stats()
        self.store.set("v3_active", None)
        LOG.info(
            "paper_closed experiment=%s id=%s outcome=%s r=%s measured=%s net_r=%.3f max_dd=%.3f",
            self.experiment["id"], trade["id"], trade.get("outcome"), trade.get("r"),
            stats.get("measured"), stats.get("net_r", 0.0), stats.get("max_drawdown_r", 0.0),
        )

    def cycle(self, now):
        bars = self.market.fetch(now)
        active = self.store.get("v3_active")
        if active:
            active, _ = advance_trade(active, bars)
            if active["status"] == "closed":
                self._finish(active)
                active = None
            else:
                self.store.set("v3_active", active)

        try:
            macro = self.global_context.snapshot(now)
            self.store.set("v3_macro", macro)
            self.store.set("v3_macro_error", self.global_context.last_error)
            if self.global_context.last_error:
                LOG.warning("macro_context_partial error=%s", self.global_context.last_error)
        except Exception as exc:
            macro = None
            detail = type(exc).__name__ + ":" + str(exc)
            self.store.set("v3_macro_error", detail)
            LOG.warning("macro_context_unavailable error=%s", detail)

        decision = analyze_v3(bars, now, macro=macro)
        self.store.set("v3_last_analysis", decision)
        self.store.set("v3_heartbeat", now.timestamp())

        allowed_news, news_reason, nearby = self.news.check(now)
        research = decision.get("v3", {})
        LOG.info(
            "analysis experiment=%s side=%s reason=%s session=%s vol=%s pct=%s macro=%s macro_score=%s coverage=%s news=%s",
            self.experiment["id"], decision.get("side"), decision.get("reason"),
            research.get("session"), research.get("volatility_regime"),
            research.get("volatility_percentile"), research.get("macro_alignment"),
            research.get("macro_score"), macro.get("coverage") if macro else None, news_reason,
        )

        if active or decision.get("side") not in ("BUY", "SELL"):
            return
        if not entry_window(now) or not allowed_news:
            return
        if now.timestamp() - self.store.get("v3_last_entry", 0) < self.cooldown:
            return
        if nearby:
            return

        require_fresh(bars, now, 120)
        quote = self.market.quote(lambda: datetime.now(UTC))
        now2 = datetime.now(UTC)
        require_fresh(bars, now2, 120)
        tolerance = min(1.0, decision["atr"] * 0.25)
        shift = quote["price"] - decision["price"]
        if abs(shift) > tolerance:
            self.store.set("v3_last_block", "market_price_moved")
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
            research_v3=research,
            macro_snapshot=macro,
            experiment_id=self.experiment["id"],
            paper_only=True,
        )
        self.store.set("v3_active", trade)
        self.store.set("v3_last_entry", now2.timestamp())
        LOG.info(
            "paper_open experiment=%s id=%s side=%s entry=%.2f session=%s vol=%s macro=%s",
            self.experiment["id"], trade["id"], trade["side"], trade["entry"],
            research.get("session"), research.get("volatility_regime"),
            research.get("macro_alignment"),
        )


def run(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(args.db)
    market = Market(args.twelve_key)
    news = NewsGuard(store)
    global_context = GlobalContextProvider(refresh_seconds=args.macro_refresh)
    paper = V3Paper(store, market, news, global_context, args.cooldown)
    LOG.info("starting isolated V3 paper worker db=%s experiment=%s", args.db, paper.experiment["id"])
    try:
        while True:
            now = datetime.now(UTC)
            try:
                paper.cycle(now)
                store.set("v3_last_error", None)
            except DataError as exc:
                store.set("v3_last_error", str(exc))
                LOG.warning("cycle_data_error reason=%s", exc)
            except Exception:
                LOG.exception("cycle_failed")
            time.sleep(args.interval)
    finally:
        store.close()


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.getenv("V3_DB_PATH", "/data/laith_v3.db"))
    p.add_argument("--twelve-key", default=os.getenv("TWELVE_DATA_API_KEY"))
    p.add_argument("--interval", type=int, default=int(os.getenv("V3_CHECK_INTERVAL_SECONDS", "900")))
    p.add_argument("--cooldown", type=int, default=int(os.getenv("V3_SIGNAL_COOLDOWN_MINUTES", "60")))
    p.add_argument("--macro-refresh", type=int, default=int(os.getenv("V3_MACRO_REFRESH_SECONDS", "21600")))
    return p


if __name__ == "__main__":
    run(parser().parse_args())
