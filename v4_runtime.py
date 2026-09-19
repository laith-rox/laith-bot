"""V4 runtime with resilient five-minute paper-signal delivery.

Official V4 entries remain strict and unchanged. Quick 5m setups use fresh
closed 5m bars for indicators and a timestamped current-slot reference for the
entry price. If the history endpoint briefly fails, one-slot recent cached bars
may still be used only when the live quote itself is current and aligned.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import math
import time

from engine import advance_trade
from market import DataError, require_fresh
from news import NewsGuard
from storage import Store
from v3_global_data import GlobalContextProvider
from v4_quick import advance_quick, build_quick, continuation_snapshot
from v4_quick_5m import analyze_quick_5m
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
QUICK_BAR_FALLBACK_ERRORS = {
    "market_http_429",
    "market_connection_failed",
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
    """Default quick entry reference; V4 group runtime replaces this with current-slot logic."""
    return quick_reference_quote(market, bars, now)


def quick_market_bars(market, now, cached_bars=None):
    """Prefer fresh provider bars; permit only a very recent cache during brief transport failures."""
    try:
        return market.fetch(now), False
    except DataError as exc:
        reason = str(exc)
        if reason not in QUICK_BAR_FALLBACK_ERRORS or not cached_bars:
            raise
        require_fresh(cached_bars, now, 360)
        LOG.warning("quick_market_fallback reason=%s source=recent_cached_5m_bars", reason)
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
    """Keep rule strength visible while downgrading confidence when important context is weaker."""
    raw_strength = setup.get("strength") or "—"
    adjusted_strength = raw_strength
    adjustments = []
    higher_side = ((decision.get("quick5m") or {}).get("higher_side")
                   or decision.get("side", "WAIT"))
    if raw_strength == "قوية" and setup.get("risk_level") == "مرتفعة":
        adjusted_strength = "متوسطة"
        adjustments.append("المخاطرة مرتفعة")
    if raw_strength == "قوية" and higher_side == "WAIT":
        adjusted_strength = "متوسطة"
        adjustments.append("الاتجاه الأكبر غير مؤكد")
    if raw_strength == "قوية" and setup.get("cached_market_data"):
        adjusted_strength = "متوسطة"
        adjustments.append("مؤشرات 5د من كاش حديث")
    setup["raw_strength"] = raw_strength
    setup["strength"] = adjusted_strength
    setup["strength_adjustments"] = list(dict.fromkeys(adjustments))
    setup["official_decision"] = higher_side
    setup["strength_is_probability"] = False
    return setup


class V4PaperResilientQuick(V4Paper):
    def quick_cycle(self, now):
        """Five-minute stream: expose weak/medium/strong candidates when data is current enough."""
        bars, cached_market = quick_market_bars(
            self.market, now, getattr(self, "_last_quick_bars", None)
        )
        if not cached_market:
            self._last_quick_bars = bars
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

        quick_decision = analyze_quick_5m(bars, entry_ref, decision)
        self.store.set("v4_quick_5m_analysis", quick_decision)
        self.store.set("v4_quick_5m_reference", entry_ref)
        quick5m = quick_decision.get("quick5m") or {}
        if not quick5m.get("entry_allowed"):
            self.store.set("v4_quick_last_block", "quick_5m_wait")
            LOG.info(
                "quick_5m_wait buy=%s/7 sell=%s/7 reason=%s candle_start=%s",
                quick_decision.get("buy"), quick_decision.get("sell"),
                quick5m.get("reason"), entry_ref.get("candle_start_iso"),
            )
            return

        observed_at = float(entry_ref.get("observed_at", now.timestamp()))
        quote_now = datetime.fromtimestamp(observed_at, UTC)
        setup = build_quick(quick_decision, quote_now, quote_price=entry_ref["price"])
        if setup is None:
            self.store.set("v4_quick_last_block", "quick_recheck_failed")
            return

        condition_names = quick_decision.get("quick_condition_names") or []
        side_checks = (quick_decision.get("checks") or {}).get(setup.get("side")) or []
        if len(condition_names) == 7 and len(side_checks) == 7:
            setup["conditions"] = [
                {"name": name, "ok": bool(ok)}
                for name, ok in zip(condition_names, side_checks)
            ]

        reasons = list(setup.get("risk_reasons") or [])
        if not allowed_news or nearby:
            reasons.append("خبر/حدث اقتصادي قريب")
            setup["risk_level"] = "مرتفعة"
        if cached_market:
            reasons.append("مؤشرات 5د مبنية على كاش حديث بسبب تعطل مؤقت في time_series")
            setup["risk_level"] = "مرتفعة"
        if entry_ref.get("candle_open_estimated"):
            reasons.append("افتتاح شمعة 5د مرجعي من إغلاق الشمعة السابقة؛ سعر الدخول نفسه حي")
        if entry_ref.get("delayed_reference"):
            reasons.append("مرجع الدخول آخر شمعة 5د مغلقة حديثة لأن السعر الحي لم يكن موثوق التوقيت")
            setup["risk_level"] = "مرتفعة"
        gate_reasons = (((quick_decision.get("v4") or {}).get("intelligence") or {}).get("entry_gate") or {}).get("reasons") or []
        for reason in gate_reasons:
            if reason not in ("recent_data_gap", "stale_market_data"):
                reasons.append(f"تحذير هيكلي: {reason}")
                setup["risk_level"] = "مرتفعة"
        try:
            atr5 = float(quick_decision["atr"])
            move_from_open = abs(float(entry_ref["price"]) - float(entry_ref["candle_open"]))
            if move_from_open > 0.35 * atr5:
                reasons.append("شمعة 5د الحالية تحركت بقوة قبل الدخول")
                setup["risk_level"] = "مرتفعة"
        except (KeyError, TypeError, ValueError):
            pass

        setup["risk_reasons"] = list(dict.fromkeys(reasons))
        setup.update(
            quote_time=entry_ref.get("time"),
            quote_source=entry_ref.get("source"),
            delayed_reference=bool(entry_ref.get("delayed_reference")),
            cached_market_data=bool(cached_market),
            candle_start=entry_ref.get("candle_start"),
            candle_start_iso=entry_ref.get("candle_start_iso"),
            candle_open=entry_ref.get("candle_open"),
            candle_high=entry_ref.get("candle_high"),
            candle_low=entry_ref.get("candle_low"),
            candle_open_estimated=bool(entry_ref.get("candle_open_estimated")),
            candle_open_source=entry_ref.get("candle_open_source"),
            signal_observed_at=entry_ref.get("observed_at"),
            entry_delay_seconds=entry_ref.get("entry_delay_seconds"),
            current_five_minute_candle=bool(entry_ref.get("current_five_minute_candle")),
            timing_aligned=bool(entry_ref.get("timing_aligned")),
            trade_slot_time=entry_ref.get("candle_start"),
            quick_timeframe="5m",
            quick5m=quick5m,
            signal_strength=quick5m.get("strength") or setup.get("strength"),
            rule_completion_percent=quick5m.get("rule_completion_percent"),
        )
        calibrate_quick_strength(setup, quick_decision)
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
            "quick_open id=%s side=%s entry=%.2f candle_start=%s delay=%ss stop=%.2f target=%.2f quick5m_buy=%s/7 quick5m_sell=%s/7 score=%s/7 strength=%s risk=%s source=%s timing_aligned=%s cached=%s official_active=%s",
            setup["id"], setup["side"], setup["entry"], setup.get("candle_start_iso"),
            setup.get("entry_delay_seconds"), setup["stop"], setup["target"],
            quick_decision.get("buy"), quick_decision.get("sell"), setup["score"],
            setup["strength"], setup.get("risk_level"), setup.get("quote_source"),
            setup.get("timing_aligned"), bool(cached_market), bool(active),
        )
        if self.notifier:
            self.notifier.send(quick_message(setup))


NY_TZ = ZoneInfo("America/New_York")


def market_weekend_closed(now):
    """Return True during the regular XAU/FX weekend closure.

    Uses New York session time so DST changes are handled automatically.
    Conservative window: Friday from 17:00 NY through Sunday before 18:00 NY.
    """
    local = now.astimezone(NY_TZ)
    weekday = local.weekday()  # Mon=0 ... Sun=6
    if weekday == 5:
        return True
    if weekday == 4 and local.hour >= 17:
        return True
    if weekday == 6 and local.hour < 18:
        return True
    return False


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
            if market_weekend_closed(now):
                # Keep Telegram polling alive, but do not request market data or
                # publish trading/monitoring messages while XAU is closed.
                store.set("v4_market_status", "WEEKEND_CLOSED")
                store.set("v4_last_error", None)
                store.set("v4_quick_last_error", None)
                next_cycle = time.time() + args.interval
                next_quick = time.time() + args.quick_interval
                time.sleep(max(1, min(args.telegram_poll, args.quick_interval, args.interval)))
                continue
            store.set("v4_market_status", "OPEN")
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
