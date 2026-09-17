"""Laith V4 entrypoint with group routing, balanced quick display, emergency alerts and H4 paper trades."""
from datetime import datetime, timezone
import logging

import v4_runtime
from v4_emergency import scan_emergencies
from v4_group_telegram import V4Telegram
from v4_h4 import process_h4
from v4_key_config import apply_v4_twelve_key_precedence
from v4_quick_balance import attach_condition_balance, quick_message as balanced_quick_message
from v4_quick_guard import guard_alert_message, guard_quick_setup
from v4_shared_market import SharedV4Market, closed_bar_reference

LOG = logging.getLogger("laith.v4.emergency")
H4_LOG = logging.getLogger("laith.v4.h4")
KEY_LOG = logging.getLogger("laith.v4.key")

_original_build_quick = v4_runtime.build_quick
_BasePaper = v4_runtime.V4PaperResilientQuick


def _build_quick_with_balance(decision, *args, **kwargs):
    setup = _original_build_quick(decision, *args, **kwargs)
    return attach_condition_balance(setup, decision)


class QuickGuardBlocked(RuntimeError):
    def __init__(self, block):
        super().__init__(str(block.get("reason") or "quick_guard_blocked"))
        self.block = block


class V4PaperWithEmergency(_BasePaper):
    """Adds quick guards, reversal warnings and a separate H4 paper stream.

    Official V4 entry logic, stops and targets remain unchanged.
    """

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

    def quick_cycle(self, now):
        try:
            result = super().quick_cycle(now)
        except QuickGuardBlocked as exc:
            self._handle_guard_block(exc.block)
            result = None

        decision = self.store.get("v4_quick_last_analysis") or {}
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

        # Independent H4 paper stream reuses the already-fetched 5m bars, so it
        # does not add another Twelve Data request and cannot alter quick/official logic.
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


# V4-only infrastructure wiring. Official, quick and H4 analyses share a single
# successful XAU/USD history fetch per five-minute slot. Quick paper entries use
# that same latest closed 5m candle as their reference, avoiding a second quote
# API call. Official V4 confirmation logic remains unchanged.
v4_runtime.Market = SharedV4Market
v4_runtime.quick_reference_quote = closed_bar_reference
v4_runtime.build_quick = _build_quick_with_balance
v4_runtime.quick_message = balanced_quick_message
v4_runtime.V4Telegram = V4Telegram
v4_runtime.V4PaperResilientQuick = V4PaperWithEmergency


if __name__ == "__main__":
    key_source = apply_v4_twelve_key_precedence()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    KEY_LOG.info("market_key_source=%s", key_source)
    if key_source != "V4_TWELVE_DATA_API_KEY":
        raise RuntimeError("V4_TWELVE_DATA_API_KEY is required for isolated V4 worker")
    v4_runtime.run(v4_runtime.parser().parse_args())
