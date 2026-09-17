"""V4 runtime with resilient five-minute paper-signal delivery.

Official V4 entries remain strict and unchanged. Existing trades can still be
monitored with usable closed/cached data, but NEW quick setups require a real
currently-forming five-minute candle from the provider whose start time matches
the quick slot. Cached/previous candles are never used to create a new quick entry.
"""
from datetime import datetime
import logging
import math
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
    """Return a reference price for monitoring without weakening official entry."""
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


def quick_entry_reference(market, bars, now):
    """Default quick entry reference; V4 group runtime replaces this with live 5m candle logic."""
    return quick_reference_quote(market, bars, now)


def quick_market_bars(market, now, cached_bars=None):
    """Prefer fresh bars; cached fallback is monitoring-only for new quick entry logic."""
    try:
        return market.fetch(now), False
    except DataError as exc:
        if str(exc) != "market_http_429" or not cached_bars:
            raise
        require_fresh(cached_bars, now, 600)
        return cached_bars, True


def quick_history_snapshot(trades):
    """Summarize observed quick-paper outcomes; this is not a forecast probability."""
    measured = []
    for trade in trades or []:
        if trade.get("status") != "closed":
            continue
        try:
            r_value = float(trade.get("r"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(r_value):
            measured.append(r_value)
    positive = sum(value > 0 for value in measured)
    negative = sum(value < 0 for value in measured)
    flat = sum(value == 0 for value in measured)
    sample = len(measured)
    return {
        "sample": sample,
        "positive": positive,
        "negative": negative,
        "flat": flat,
        "positive_rate": round(positive / sample * 100) if sample else None,
    }


def calibrate_quick_strength(setup, decision):
    """Keep raw rule completion, but do not call a risky or official-WAIT setup strong."""
    raw_strength = setup.get("strength") or "—"
    adjusted_strength = raw_strength
    adjustments = []
    if raw_strength == "قوية" and setup.get("risk_level") == "مرتفعة":
        adjusted_strength = "متوسطة"
        adjustments.append("المخاطرة مرتفعة")
    if raw_strength == "قوية" and decision.get("side") == "WAIT":
        adjusted_strength = "متوسطة"
        adjustments.append("النظام الرسمي WAIT")
    setup["raw_strength"] = raw_strength
    setup["strength"] = adjusted_strength
    setup["strength_adjustments"] = list(dict.fromkeys(adjustments))
    setup["official_decision"] = decision.get("side", "WAIT")
    return setup


class V4PaperResilientQuick(V4Paper):
    def quick_cycle(self, now):
        """Five-minute stream: monitor broadly, but open quick setups only on an aligned live candle."""
        bars, cached_market = quick_market_bars(
            self.market, now, getattr(self, "_last_quick_bars", None)
        )
        if not cached_market:
            self._last_quick_bars = bars
        else:
            LOG.warning("quick_market_fallback reason=market_http_429 source=cached_5m_bars monitoring_only=true")
        self._advance_quicks(bars, now)

        slot = int(now.timestamp() // 300)
        if self.store.get("v4_quick_last_slot") == slot:
            return
        self.store.set("v4_quick_last_slot", slot)

        macro = self.store.get("v4_macro")
        decision = analyze_v4(bars, now, macro=macro)
        self.store.set("v4_quick_last_analysis", decision)

        active = self.store.get("v4_active")
        monitor_quote = None
        if active:
            active, _ = advance_trade(active, bars)
            if active["status"] == "closed":
                self._finish(active)
                active = None
            else:
                self.store.set("v4_active", active)

        if active:
            monitor_quote = quick_reference_quote(self.market, bars, now)
            snap = continuation_snapshot(decision, active, price=monitor_quote["price"])
            if snap:
                snap.update(
                    time=datetime.now(UTC).isoformat(),
                    quote_source=monitor_quote.get("source"),
                    delayed_reference=bool(monitor_quote.get("delayed_reference")),
                )
                self.store.set("v4_last_continuation", snap)
                LOG.info(
                    "official_continuation side=%s state=%s score=%s/7 price=%.2f rsi=%s source=%s",
                    snap.get("side"), snap.get("state"), snap.get("score"),
                    snap.get("price"), snap.get("rsi"), snap.get("quote_source"),
                )
                if self.notifier:
                    self.notifier.send(continuation_message(snap))

        allowed_news, news_reason, nearby = self.news.check(now)
        setup_preview = build_quick(decision, now)
        if setup_preview is None:
            self.store.set("v4_quick_last_block", "quick_data_incomplete")
            return

        # Cached bars may keep monitoring alive, but they can never create a NEW
        # quick setup. Laith requested a real 5m candle for every quick trade.
        if cached_market:
            self.store.set("v4_quick_last_block", "quick_requires_live_current_candle")
            LOG.warning("quick_entry_block reason=quick_requires_live_current_candle cached_market=true")
            return

        try:
            entry_ref = quick_entry_reference(self.market, bars, now)
        except DataError as exc:
            reason = str(exc)
            self.store.set("v4_quick_last_block", reason)
            LOG.warning("quick_entry_block reason=%s", reason)
            return

        if not entry_ref.get("timing_aligned"):
            self.store.set("v4_quick_last_block", "quick_candle_time_not_aligned")
            LOG.warning("quick_entry_block reason=quick_candle_time_not_aligned")
            return

        observed_at = float(entry_ref.get("observed_at", now.timestamp()))
        quote_now = datetime.fromtimestamp(observed_at, UTC)
        setup = build_quick(decision, quote_now, quote_price=entry_ref["price"])
        if setup is None:
            self.store.set("v4_quick_last_block", "quick_recheck_failed")
            return

        reasons = list(setup.get("risk_reasons") or [])
        if not allowed_news or nearby:
            reasons.append("خبر/حدث اقتصادي قريب")
            setup["risk_level"] = "مرتفعة"
        try:
            tolerance = min(1.0, float(decision["atr"]) * 0.25)
            if abs(float(entry_ref["price"]) - float(decision["price"])) > tolerance:
                reasons.append("سعر الشمعة الحالية تحرك عن آخر سعر تحليل مغلق")
                setup["risk_level"] = "مرتفعة"
        except (KeyError, TypeError, ValueError):
            pass

        setup["risk_reasons"] = list(dict.fromkeys(reasons))
        setup.update(
            quote_time=entry_ref.get("time"),
            quote_source=entry_ref.get("source"),
            delayed_reference=False,
            cached_market_data=False,
            candle_start=entry_ref.get("candle_start"),
            candle_start_iso=entry_ref.get("candle_start_iso"),
            candle_open=entry_ref.get("candle_open"),
            signal_observed_at=entry_ref.get("observed_at"),
            entry_delay_seconds=entry_ref.get("entry_delay_seconds"),
            current_five_minute_candle=True,
            timing_aligned=True,
            trade_slot_time=entry_ref.get("candle_start"),
        )
        calibrate_quick_strength(setup, decision)
        history = quick_history_snapshot(self._quick_rows())
        setup.update(
            historical_sample=history["sample"],
            historical_positive=history["positive"],
            historical_negative=history["negative"],
            historical_flat=history["flat"],
            historical_positive_rate=history["positive_rate"],
        )
        self._save_quick(setup)
        self.store.set("v4_quick_last", setup)
        self.store.set("v4_quick_last_block", None)
        LOG.info(
            "quick_open id=%s side=%s entry=%.2f candle_start=%s delay=%ss stop=%.2f target=%.2f score=%s/7 strength=%s raw_strength=%s risk=%s hist_positive=%s/%s source=%s timing_aligned=%s official_active=%s",
            setup["id"], setup["side"], setup["entry"], setup.get("candle_start_iso"),
            setup.get("entry_delay_seconds"), setup["stop"], setup["target"], setup["score"],
            setup["strength"], setup.get("raw_strength"), setup.get("risk_level"),
            setup.get("historical_positive"), setup.get("historical_sample"), setup.get("quote_source"),
            setup.get("timing_aligned"), bool(active),
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
