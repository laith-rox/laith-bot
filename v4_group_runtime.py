"""Laith V4 entrypoint with smart guards, group routing, emergency alerts and H4 paper trades."""
from datetime import datetime, timezone
import logging

import v4_runtime
import v4_service
from v4_emergency import scan_emergencies
from v4_group_telegram import V4Telegram
from v4_h4 import process_h4
from v4_intelligence import (
    attach_continuation_intelligence,
    enhance_continuation_message,
    enhance_paper_close_message,
    enhance_paper_open_message,
    quick_hard_blocked,
)
from v4_key_config import apply_v4_twelve_key_precedence
from v4_learning import classify_trade_lesson, record_trade_lesson
from v4_quick_balance import attach_condition_balance, quick_message as balanced_quick_message
from v4_quick_guard import guard_alert_message, guard_quick_setup
from v4_shared_market import SharedV4Market, closed_bar_reference
from v4_wait_display import smart_wait_message

LOG = logging.getLogger("laith.v4.emergency")
H4_LOG = logging.getLogger("laith.v4.h4")
KEY_LOG = logging.getLogger("laith.v4.key")
LEARN_LOG = logging.getLogger("laith.v4.learning")

_original_build_quick = v4_runtime.build_quick
_original_continuation_snapshot = v4_runtime.continuation_snapshot
_original_continuation_message = v4_runtime.continuation_message
_original_paper_open_message = v4_service.paper_open_message
_original_paper_close_message = v4_service.paper_close_message
_BasePaper = v4_runtime.V4PaperResilientQuick


def _build_quick_with_balance(decision, *args, **kwargs):
    # A V4 smart hard block means WAIT, not a high-risk quick entry. News risk
    # remains separately visible in the resilient quick stream.
    if quick_hard_blocked(decision):
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


def _shared_quick_entry_reference(market, _bars, now):
    """New quick entries require the real current 5m candle and an aligned slot start."""
    return market.current_candle_reference(now)


class QuickGuardBlocked(RuntimeError):
    def __init__(self, block):
        super().__init__(str(block.get("reason") or "quick_guard_blocked"))
        self.block = block


class V4PaperWithEmergency(_BasePaper):
    """Adds smart waits, quick guards, learning, reversal warnings and H4 paper trades."""

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

    def _send_smart_wait(self, decision, now):
        if not self.notifier or not decision or not quick_hard_blocked(decision):
            return
        slot = int(now.timestamp() // 300)
        if self.store.get("v4_smart_wait_slot") == slot:
            return
        try:
            allowed_news, news_reason, nearby = self.news.check(now)
        except Exception:
            allowed_news, news_reason, nearby = False, "calendar_unavailable", []
        extra = self.store.get("v4_quick_last_block")
        self.notifier.send(
            smart_wait_message(
                decision,
                news_reason=news_reason,
                nearby=bool(nearby) or not allowed_news,
                extra_reason=extra,
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

        # Independent H4 paper stream reuses the already-fetched 5m CLOSED bars,
        # so it does not add another Twelve Data request or consume the forming
        # candle as if it were a completed H4 observation.
        bars = getattr(self, "_last_quick_bars", None)
        if bars:
            try:
                h4_events = process_h4(self.store, self.notifier, bars, now)
                for event in h4_events:
                    kind = event.get("kind")
                    trade = event.get("trade") or {}
                    h4_decision = event.get("decision") or {}
                    H4_LOG.info(
                        "h4_event kind=%s id=%s side=%s buy=%s/7 sell=%s/7 outcome=%s",
                        kind, trade.get("id"), trade.get("side") or h4_decision.get("side"),
                        h4_decision.get("buy"), h4_decision.get("sell"), trade.get("outcome"),
                    )
            except Exception:
                H4_LOG.exception("h4_cycle_failed")
        return result


# V4-only infrastructure wiring. Official/H4 analysis remains based on closed
# bars. New quick entries are additionally tied to the real current 5m candle and
# only accepted when its provider timestamp matches the current five-minute slot.
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
