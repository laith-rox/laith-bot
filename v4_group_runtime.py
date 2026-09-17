"""Laith V4 entrypoint with group mirroring, balanced quick display and emergency alerts."""
import logging

import v4_runtime
from v4_emergency import scan_emergencies
from v4_group_telegram import V4Telegram
from v4_quick_balance import attach_condition_balance, quick_message as balanced_quick_message

LOG = logging.getLogger("laith.v4.emergency")

_original_build_quick = v4_runtime.build_quick
_BasePaper = v4_runtime.V4PaperResilientQuick


def _build_quick_with_balance(decision, *args, **kwargs):
    setup = _original_build_quick(decision, *args, **kwargs)
    return attach_condition_balance(setup, decision)


class V4PaperWithEmergency(_BasePaper):
    """Adds read-only reversal warnings; trade logic and lifecycle stay unchanged."""

    def quick_cycle(self, now):
        result = super().quick_cycle(now)
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
