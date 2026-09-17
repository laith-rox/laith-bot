"""Laith V4 runtime with optional MT5 execution bridge.

This wrapper leaves V4 analysis unchanged and only mirrors fresh official paper
entries into the fail-closed MT5 bridge when explicitly enabled.
"""
import logging

import v4_group_runtime
import v4_runtime
from v4_mt5_bridge import publish_official_order, start_bridge_server

LOG = logging.getLogger("laith.v4.mt5.runtime")

_BasePaper = v4_group_runtime.V4PaperWithEmergency


class V4PaperWithMT5Bridge(_BasePaper):
    def cycle(self, now):
        result = super().cycle(now)
        active = self.store.get("v4_active")
        if active:
            try:
                publish_official_order(self.store, active)
            except Exception:
                # Execution transport must never change V4's analysis/paper behavior.
                LOG.exception("execution_bridge_publish_failed")
        return result


# v4_group_runtime already wires all V4-only market/Telegram/guard behavior.
# We replace only the paper class with the bridge-aware subclass.
v4_runtime.V4PaperResilientQuick = V4PaperWithMT5Bridge


if __name__ == "__main__":
    key_source = v4_group_runtime.apply_v4_twelve_key_precedence()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if key_source != "V4_TWELVE_DATA_API_KEY":
        raise RuntimeError("V4_TWELVE_DATA_API_KEY is required for isolated V4 worker")
    args = v4_runtime.parser().parse_args()
    start_bridge_server(args.db)
    v4_runtime.run(args)
