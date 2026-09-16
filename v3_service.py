"""Standalone V3 paper-trading worker.

Safe isolation rules:
- separate SQLite database by default (/data/laith_v3.db),
- no Telegram transport,
- no broker orders,
- no writes to the live bot database,
- research/v3-signal-lab branch only until explicitly promoted.
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
from v3_research import analyze_v3

UTC = timezone.utc
LOG = logging.getLogger("laith.v3")


class V3Paper:
    def __init__(self, store, market, news, cooldown_minutes=60):
        self.store = store
        self.market = market
        self.news = news
        self.cooldown = cooldown_minutes * 60
        self.store.db.execute(
            "CREATE TABLE IF NOT EXISTS v3_paper(id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        self.store.db.commit()

    def _finish(self, trade):
        with self.store.db:
            self.store.db.execute(
                "INSERT OR IGNORE INTO v3_paper(id,data) VALUES (?,?)",
                (trade["id"], json.dumps(trade, allow_nan=False)),
            )
        stats = self.store.get("v3_stats", {"closed": 0, "measured": 0, "net_r": 0.0})
        stats["closed"] += 1
        if trade.get("r") is not None:
            stats["measured"] += 1
            stats["net_r"] += trade["r"]
        self.store.set("v3_stats", stats)
        self.store.set("v3_active", None)
        LOG.info("paper_closed id=%s outcome=%s r=%s", trade["id"], trade.get("outcome"), trade.get("r"))

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

        decision = analyze_v3(bars, now)
        self.store.set("v3_last_analysis", decision)
        self.store.set("v3_heartbeat", now.timestamp())

        allowed_news, news_reason, nearby = self.news.check(now)
        research = decision.get("v3", {})
        LOG.info(
            "analysis side=%s reason=%s session=%s vol=%s pct=%s news=%s",
            decision.get("side"), decision.get("reason"), research.get("session"),
            research.get("volatility_regime"), research.get("volatility_percentile"), news_reason,
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
            paper_only=True,
        )
        self.store.set("v3_active", trade)
        self.store.set("v3_last_entry", now2.timestamp())
        LOG.info("paper_open id=%s side=%s entry=%.2f", trade["id"], trade["side"], trade["entry"])


def run(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(args.db)
    market = Market(args.twelve_key)
    news = NewsGuard(store)
    paper = V3Paper(store, market, news, args.cooldown)
    LOG.info("starting isolated V3 paper worker db=%s", args.db)
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
    p.add_argument("--interval", type=int, default=int(os.getenv("V3_CHECK_INTERVAL_SECONDS", "30")))
    p.add_argument("--cooldown", type=int, default=int(os.getenv("V3_SIGNAL_COOLDOWN_MINUTES", "60")))
    return p


if __name__ == "__main__":
    run(parser().parse_args())
