"""Laith V4 entrypoint with group routing, balanced quick display and emergency alerts."""
from datetime import datetime, timezone
import logging

import v4_runtime
from v4_emergency import scan_emergencies
from v4_group_telegram import V4Telegram
from v4_quick_balance import attach_condition_balance, quick_message as balanced_quick_message
from v4_quick_guard import guard_alert_message, guard_quick_setup

LOG = logging.getLogger("laith.v4.emergency")

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
    """Adds approved quick guards plus read-only reversal warnings.

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
        if not decision:
            return result
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
        return result


v4_runtime.build_quick = _build_quick_with_balance
v4_runtime.quick_message = balanced_quick_message
v4_runtime.V4Telegram = V4Telegram
v4_runtime.V4PaperResilientQuick = V4PaperWithEmergency


if __name__ == "__main__":
    v4_runtime.run(v4_runtime.parser().parse_args())
