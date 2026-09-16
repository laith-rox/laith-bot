"""V4 runtime with resilient five-minute paper-signal delivery.

Official V4 entries remain strict and unchanged. The quick paper stream runs
around the clock while market data are usable. It may fall back to the latest
closed/cached five-minute data when Twelve Data is stale, unavailable, or
rate-limited; every such fallback is explicitly marked high risk.
"""
from datetime import datetime
import logging
import time

from engine import advance_trade
from market import DataError, require_fresh
from news import NewsGuard
from storage import Store
from v3_global_data import GlobalContextProvider
from v4_quick import advance_quick, build_quick, continuation_snapshot
from v4_research import analyze_v4
from v4_service import V4Paper, UTC, parser
from v4_telegram import V4Telegram, continuation_message, quick_message
from market import Market

LOG = logging.getLogger("laith.v4")

QUICK_QUOTE_FALLBACK_ERRORS = {
    "market_quote_stale",
    "market_quote_unavailable",
    "market_http_429",
}


def quick_reference_quote(market, bars, now):
    """Return a reference price for paper monitoring without weakening official entry."""
    try:
        quote = market.quote(lambda: datetime.now(UTC))
        quote["delayed_reference"] = False
        return quote
    except DataError as exc:
        if str(exc) not in QUICK_QUOTE_FALLBACK_ERRORS:
            raise
        require_fresh(bars, now, 600)
        last = bars[-1]
        return {
            "price": float(last.close),
            "time": last.end.timestamp(),
            "source": "آخر شمعة 5د مغلقة",
            "delayed_reference": True,
        }


def quick_market_bars(market, now, cached_bars=None):
    """Prefer fresh bars; on Twelve Data 429 reuse only a still-fresh cached set."""
    try:
        return market.fetch(now), False
    except DataError as exc:
        if str(exc) != "market_http_429" or not cached_bars:
            raise
        require_fresh(cached_bars, now, 600)
        return cached_bars, True


class V4PaperResilientQuick(V4Paper):
    def quick_cycle(self, now):
        """Five-minute paper stream: emit setups 24h whenever usable data exist."""
        bars, cached_market = quick_market_bars(
            self.market, now, getattr(self, "_last_quick_bars", None)
        )
        if not cached_market:
            self._last_quick_bars = bars
        else:
            LOG.warning("quick_market_fallback reason=market_http_429 source=cached_5m_bars")
        self._advance_quicks(bars, now)

        slot = int(now.timestamp() // 300)
        if self.store.get("v4_quick_last_slot") == slot:
            return
        self.store.set("v4_quick_last_slot", slot)

        macro = self.store.get("v4_macro")
        decision = analyze_v4(bars, now, macro=macro)
        self.store.set("v4_quick_last_analysis", decision)

        active = self.store.get("v4_active")
        quote = None
        if active:
            active, _ = advance_trade(active, bars)
            if active["status"] == "closed":
                self._finish(active)
                active = None
            else:
                self.store.set("v4_active", active)

        if active:
            quote = quick_reference_quote(self.market, bars, now)
            snap = continuation_snapshot(decision, active, price=quote["price"])
            if snap:
                snap.update(
                    time=datetime.now(UTC).isoformat(),
                    quote_source=quote.get("source"),
                    delayed_reference=bool(quote.get("delayed_reference")),
                )
                self.store.set("v4_last_continuation", snap)
                LOG.info(
                    "official_continuation side=%s state=%s score=%s/7 price=%.2f rsi=%s source=%s",
                    snap.get("side"), snap.get("state"), snap.get("score"),
                    snap.get("price"), snap.get("rsi"), snap.get("quote_source"),
                )
                if self.notifier:
                    self.notifier.send(continuation_message(snap))

        # Quick setups intentionally have no general entry-window restriction.
        # Market/data freshness remains the hard gate, so closed/stale markets do not
        # produce a supposedly live quick setup.
        allowed_news, news_reason, nearby = self.news.check(now)
        setup_preview = build_quick(decision, now)
        if setup_preview is None:
            self.store.set("v4_quick_last_block", "quick_data_incomplete")
            return

        if quote is None:
            quote = quick_reference_quote(self.market, bars, now)
        quote_now = datetime.now(UTC)
        setup = build_quick(decision, quote_now, quote_price=quote["price"])
        if setup is None:
            self.store.set("v4_quick_last_block", "quick_recheck_failed")
            return

        reasons = list(setup.get("risk_reasons") or [])
        if cached_market:
            reasons.append("بيانات الشموع من آخر قراءة مخزنة بسبب حد Twelve Data")
            setup["risk_level"] = "مرتفعة"
        if quote.get("delayed_reference"):
            reasons.append("السعر المرجعي من آخر شمعة 5د لأن السعر اللحظي متأخر/غير متاح")
            setup["risk_level"] = "مرتفعة"
        if not allowed_news or nearby:
            reasons.append("خبر/حدث اقتصادي قريب")
            setup["risk_level"] = "مرتفعة"
        try:
            tolerance = min(1.0, float(decision["atr"]) * 0.25)
            if abs(float(quote["price"]) - float(decision["price"])) > tolerance:
                reasons.append("السعر تحرك عن سعر التحليل")
                setup["risk_level"] = "مرتفعة"
        except (KeyError, TypeError, ValueError):
            pass

        setup["risk_reasons"] = list(dict.fromkeys(reasons))
        setup.update(
            quote_time=quote.get("time"),
            quote_source=quote.get("source"),
            delayed_reference=bool(quote.get("delayed_reference")),
            cached_market_data=bool(cached_market),
        )
        self._save_quick(setup)
        self.store.set("v4_quick_last", setup)
        self.store.set("v4_quick_last_block", None)
        LOG.info(
            "quick_open id=%s side=%s entry=%.2f stop=%.2f target=%.2f score=%s/7 strength=%s risk=%s source=%s cached=%s official_active=%s",
            setup["id"], setup["side"], setup["entry"], setup["stop"], setup["target"],
            setup["score"], setup["strength"], setup.get("risk_level"), setup.get("quote_source"),
            bool(cached_market), bool(active),
        )
        if self.notifier:
            self.notifier.send(quick_message(setup))


def run(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(args.db)
    market = Market(args.twelve_key)
    news = NewsGuard(store)
    telegram = V4Telegram(args.telegram_token, store, args.telegram_chat, args.telegram_pair_code)
    global_context = GlobalContextProvider(refresh_seconds=args.macro_refresh, twelve_key=args.twelve_key)
    paper = V4PaperResilientQuick(store, market, news, global_context, args.cooldown, notifier=telegram)
    LOG.info(
        "starting independent V4 resilient worker db=%s experiment=%s telegram=%s quick_interval=%ss",
        args.db, paper.experiment["id"], bool(args.telegram_token), args.quick_interval,
    )
    next_cycle = 0.0
    next_quick = 0.0
    try:
        while True:
            now = datetime.now(UTC)
            try:
                telegram.poll()
            except Exception:
                LOG.exception("telegram_cycle_failed")
            if time.time() >= next_cycle:
                try:
                    paper.cycle(now)
                    store.set("v4_last_error", None)
                except DataError as exc:
                    store.set("v4_last_error", str(exc))
                    LOG.warning("cycle_data_error reason=%s", exc)
                except Exception:
                    LOG.exception("cycle_failed")
                next_cycle = time.time() + args.interval
            if time.time() >= next_quick:
                try:
                    paper.quick_cycle(datetime.now(UTC))
                    store.set("v4_quick_last_error", None)
                except DataError as exc:
                    store.set("v4_quick_last_error", str(exc))
                    LOG.warning("quick_cycle_data_error reason=%s", exc)
                except Exception:
                    LOG.exception("quick_cycle_failed")
                current = time.time()
                next_quick = (int(current) // args.quick_interval + 1) * args.quick_interval + 12
            time.sleep(max(1, min(args.telegram_poll, args.quick_interval, args.interval)))
    finally:
        store.close()


if __name__ == "__main__":
    run(parser().parse_args())
