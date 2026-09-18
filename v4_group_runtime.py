"""Laith V4 entrypoint focused on quick 5m and official 15m trade streams."""
from datetime import datetime, timezone
import logging

import v4_runtime
import v4_service
from v4_emergency import scan_emergencies
from v4_group_telegram import V4Telegram
from v4_intelligence import (
    attach_continuation_intelligence,
    enhance_continuation_message,
    enhance_paper_close_message,
    enhance_paper_open_message,
    quick_hard_blocked,
)
from v4_key_config import apply_v4_twelve_key_precedence
from v4_learning import classify_trade_lesson, record_trade_lesson
from v4_quick_5m import quick_5m_wait_message
from v4_quick_balance import attach_condition_balance, quick_message as balanced_quick_message
from v4_quick_guard import guard_alert_message, guard_quick_setup
from v4_shared_market import SharedV4Market, closed_bar_reference
from v4_wait_display import smart_wait_message
from market import DataError

LOG = logging.getLogger("laith.v4.emergency")
KEY_LOG = logging.getLogger("laith.v4.key")
LEARN_LOG = logging.getLogger("laith.v4.learning")

_original_build_quick = v4_runtime.build_quick
_original_continuation_snapshot = v4_runtime.continuation_snapshot
_original_continuation_message = v4_runtime.continuation_message
_original_paper_open_message = v4_service.paper_open_message
_original_paper_close_message = v4_service.paper_close_message
_BasePaper = v4_runtime.V4PaperResilientQuick

DATA_HARD_BLOCKS = {"recent_data_gap", "stale_market_data"}


def _quick_data_hard_blocked(decision):
    intelligence = ((decision.get("v4") or {}).get("intelligence") or {})
    reasons = ((intelligence.get("entry_gate") or {}).get("reasons") or [])
    return any(reason in DATA_HARD_BLOCKS for reason in reasons)


def _build_quick_with_balance(decision, *args, **kwargs):
    # Quick candidates remain visible through market-risk warnings so Laith can
    # decide manually. Only genuinely unsafe/stale/gapped data hides the signal.
    if _quick_data_hard_blocked(decision):
        return None
    setup = _original_build_quick(decision, *args, **kwargs)
    return attach_condition_balance(setup, decision)


def _continuation_with_intelligence(decision, trade, price=None):
    snapshot = _original_continuation_snapshot(decision, trade, price=price)
    return attach_continuation_intelligence(snapshot, decision, trade)


def _continuation_message_with_intelligence(snapshot):
    return enhance_continuation_message(_original_continuation_message(snapshot), snapshot)


def _paper_open_message_with_intelligence(trade):
    return enhance_paper_open_message(_original_paper_open_message(trade), trade)


def _paper_close_message_with_intelligence(trade, stats):
    return enhance_paper_close_message(_original_paper_close_message(trade, stats), trade)


def _shared_quick_reference(_market, bars, now):
    """Use the latest closed 5m candle for continuity monitoring without an extra API call."""
    return closed_bar_reference(bars, now)


def _shared_quick_entry_reference(market, bars, now):
    """Prefer a live current-slot reference; fall back to the just-closed 5m bar.

    The original Laith signal bot makes decisions from completed fresh candles.
    V4 keeps the live reference when Twelve Data exposes it, but must not suppress
    the entire quick stream merely because the provider omits the forming candle
    or serves a quote timestamp that is not the current 5m slot.
    """
    try:
        return market.current_candle_reference(now)
    except DataError as exc:
        if not bars:
            raise
        last = bars[-1]
        age = (now - last.end).total_seconds()
        if age < 0 or age > 90:
            raise
        LOG.warning(
            "quick_entry_reference_fallback source=latest_closed_5m live_reason=%s age=%.1fs bar_end=%s",
            exc, age, last.end.isoformat(),
        )
        return {
            "price": float(last.close),
            "candle_open": float(last.open),
            "candle_high": float(last.high),
            "candle_low": float(last.low),
            "time": last.end.timestamp(),
            "candle_start": last.start.timestamp(),
            "candle_start_iso": last.start.isoformat(),
            "observed_at": last.end.timestamp(),
            "entry_delay_seconds": round(age, 3),
            "source": "آخر شمعة 5د مغلقة حديثة — fallback موثوق",
            "delayed_reference": True,
            "shared_candle_reference": True,
            "current_five_minute_candle": False,
            "timing_aligned": True,
            "candle_open_estimated": False,
            "candle_open_source": "افتتاح آخر شمعة 5د مغلقة",
        }


class QuickGuardBlocked(RuntimeError):
    def __init__(self, block):
        super().__init__(str(block.get("reason") or "quick_guard_blocked"))
        self.block = block


class V4PaperWithEmergency(_BasePaper):
    """Adds quick guards, learning and reversal warnings to 5m/15m V4."""

    def _save_quick(self, trade):
        try:
            stamp = float(trade.get("announced", trade.get("created")))
        except (TypeError, ValueError):
            stamp = datetime.now(timezone.utc).timestamp()
        now = datetime.fromtimestamp(stamp, timezone.utc)
        block = guard_quick_setup(trade, self._quick_rows(), now)
        if not block.get("allowed"):
            raise QuickGuardBlocked(block)
        return super()._save_quick(trade)

    def _finish(self, trade):
        annotated = dict(trade)
        lesson = classify_trade_lesson(annotated)
        if lesson:
            annotated["learning"] = lesson
            record_trade_lesson(self.store, annotated, "official")
            LEARN_LOG.warning(
                "official_loss_lesson id=%s reason=%s r=%s breakout=%s vol=%s confidence=%s",
                annotated.get("id"), lesson.get("reason"), lesson.get("r"),
                lesson.get("breakout"), lesson.get("volatility"), lesson.get("confidence"),
            )
        return super()._finish(annotated)

    def _record_quick_lessons(self):
        for trade in self._quick_rows():
            if trade.get("status") != "closed":
                continue
            lesson = classify_trade_lesson(trade)
            if not lesson:
                continue
            record_trade_lesson(self.store, trade, "quick")

    def _handle_guard_block(self, block):
        self.store.set("v4_quick_last_block", block.get("reason"))
        LOG.warning(
            "quick_guard_block reason=%s side=%s detail=%s",
            block.get("reason"), block.get("side"), block.get("detail"),
        )
        if block.get("reason") != "stop_cooldown" or not self.notifier:
            return
        fingerprints = self.store.get("v4_quick_guard_alerts", {}) or {}
        if not isinstance(fingerprints, dict):
            fingerprints = {}
        side = str(block.get("side") or "UNKNOWN")
        fingerprint = block.get("fingerprint")
        if fingerprint and fingerprints.get(side) == fingerprint:
            return
        self.notifier.send(guard_alert_message(block))
        if fingerprint:
            fingerprints[side] = fingerprint
            self.store.set("v4_quick_guard_alerts", fingerprints)

    def _send_quick_5m_wait(self, _higher_decision, now):
        if not self.notifier or self.store.get("v4_quick_last_block") != "quick_5m_wait":
            return
        slot = int(now.timestamp() // 300)
        if self.store.get("v4_quick_5m_wait_slot") == slot:
            return
        decision = self.store.get("v4_quick_5m_analysis") or {}
        reference = self.store.get("v4_quick_5m_reference") or {}
        message = quick_5m_wait_message(decision, reference)
        if message:
            self.notifier.send(message)
            self.store.set("v4_quick_5m_wait_slot", slot)

    def _send_smart_wait(self, decision, now):
        # Do not send a generic higher-timeframe WAIT on top of a valid quick
        # candidate or a dedicated Quick-5m WAIT; that was confusing in Telegram.
        last_block = self.store.get("v4_quick_last_block")
        if last_block in (None, "quick_5m_wait"):
            return
        if not self.notifier or not decision or not quick_hard_blocked(decision):
            return
        slot = int(now.timestamp() // 300)
        if self.store.get("v4_smart_wait_slot") == slot:
            return
        try:
            allowed_news, news_reason, nearby = self.news.check(now)
        except Exception:
            allowed_news, news_reason, nearby = False, "calendar_unavailable", []
        self.notifier.send(
            smart_wait_message(
                decision,
                news_reason=news_reason,
                nearby=bool(nearby) or not allowed_news,
                extra_reason=last_block,
            )
        )
        self.store.set("v4_smart_wait_slot", slot)
        self.store.set(
            "v4_last_wait_plan",
            ((decision.get("v4") or {}).get("intelligence") or {}).get("wait_plan"),
        )

    def quick_cycle(self, now):
        try:
            result = super().quick_cycle(now)
        except QuickGuardBlocked as exc:
            self._handle_guard_block(exc.block)
            result = None

        decision = self.store.get("v4_quick_last_analysis") or {}
        self._send_quick_5m_wait(decision, now)
        self._send_smart_wait(decision, now)
        self._record_quick_lessons()

        if decision:
            alerts = scan_emergencies(
                self.store,
                self.notifier,
                decision,
                self.store.get("v4_active"),
                self._quick_rows(),
                now,
            )
            for alert in alerts:
                LOG.warning(
                    "emergency_reversal trade_id=%s kind=%s side=%s severity=%s own=%s/7 opposite=%s/7",
                    alert.get("trade_id"), alert.get("kind"), alert.get("side"), alert.get("severity"),
                    alert.get("own_score"), alert.get("opposite_score"),
                )

        # H4 trade processing remains disabled. V4 focuses on quick 5m + official 15m.
        return result


v4_runtime.Market = SharedV4Market
v4_runtime.quick_reference_quote = _shared_quick_reference
v4_runtime.quick_entry_reference = _shared_quick_entry_reference
v4_runtime.build_quick = _build_quick_with_balance
v4_runtime.continuation_snapshot = _continuation_with_intelligence
v4_runtime.continuation_message = _continuation_message_with_intelligence
v4_runtime.quick_message = balanced_quick_message
v4_runtime.V4Telegram = V4Telegram
v4_runtime.V4PaperResilientQuick = V4PaperWithEmergency
v4_service.paper_open_message = _paper_open_message_with_intelligence
v4_service.paper_close_message = _paper_close_message_with_intelligence


if __name__ == "__main__":
    key_source = apply_v4_twelve_key_precedence()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    KEY_LOG.info("market_key_source=%s", key_source)
    if key_source != "V4_TWELVE_DATA_API_KEY":
        raise RuntimeError("V4_TWELVE_DATA_API_KEY is required for isolated V4 worker")
    v4_runtime.run(v4_runtime.parser().parse_args())
