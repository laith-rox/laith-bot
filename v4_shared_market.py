"""V4-only shared market cache to reduce Twelve Data credit usage.

This module is intentionally isolated from the old bot and V3. One XAU/USD
5-minute history request is shared by V4 official, quick, and H4 analysis inside
the same five-minute slot. Trading rules are not changed here.
"""
from datetime import timezone
import logging

from market import Market, require_fresh

UTC = timezone.utc
LOG = logging.getLogger("laith.v4.market")


class SharedV4Market(Market):
    """Cache one successful 5m history fetch per five-minute UTC slot."""

    def __init__(self, key, session=None):
        super().__init__(key, session=session)
        self._shared_bars = None
        self._shared_slot = None
        self.provider_fetches = 0
        self.cache_hits = 0

    @staticmethod
    def _slot(now):
        return int(now.timestamp() // 300)

    def fetch(self, now):
        slot = self._slot(now)
        if self._shared_bars is not None and self._shared_slot == slot:
            # Same freshness gate used by the normal market path. Never serve
            # stale data merely to save credits.
            require_fresh(self._shared_bars, now, 600)
            self.cache_hits += 1
            LOG.info(
                "shared_market source=cache slot=%s provider_fetches=%s cache_hits=%s",
                slot, self.provider_fetches, self.cache_hits,
            )
            return self._shared_bars

        bars = super().fetch(now)
        self._shared_bars = bars
        self._shared_slot = slot
        self.provider_fetches += 1
        LOG.info(
            "shared_market source=provider slot=%s provider_fetches=%s cache_hits=%s",
            slot, self.provider_fetches, self.cache_hits,
        )
        return bars


def closed_bar_reference(bars, now):
    """Reference quick-paper entry to the latest closed fresh 5m candle.

    This avoids a separate /exchange_rate request for the quick stream. It is a
    paper reference only; official V4 entry confirmation remains unchanged.
    """
    require_fresh(bars, now, 600)
    last = bars[-1]
    return {
        "price": float(last.close),
        "time": last.end.timestamp(),
        "source": "آخر شمعة 5د مغلقة - بيانات V4 المشتركة",
        "delayed_reference": False,
        "shared_candle_reference": True,
    }
