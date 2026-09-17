"""V4-only shared XAU/USD market snapshot.

One Twelve Data 5-minute history request is shared by V4 official, quick, and H4
analysis inside the same five-minute slot.  Unlike the generic Market adapter,
this V4-only adapter also retains the provider's currently-forming five-minute
candle so quick paper setups can be tied to the real candle that opened in the
same slot.  Closed candles remain the only input to the strategy indicators.
"""
from datetime import datetime, timezone
import logging

import requests

from market import (
    DataError,
    Market,
    _quota_diagnostics,
    closed_only,
    parse_bars,
    require_fresh,
)

UTC = timezone.utc
LOG = logging.getLogger("laith.v4.market")


class SharedV4Market(Market):
    """Cache one provider snapshot per five-minute UTC slot.

    The returned value from ``fetch`` is still CLOSED candles only.  The current
    forming candle is retained separately and can be requested through
    ``current_candle_reference`` for a time-aligned quick setup.
    """

    def __init__(self, key, session=None):
        super().__init__(key, session=session)
        self._shared_bars = None
        self._shared_current_bar = None
        self._shared_slot = None
        self._current_retry_slot = None
        self.provider_fetches = 0
        self.cache_hits = 0

    @staticmethod
    def _slot(now):
        return int(now.timestamp() // 300)

    @staticmethod
    def _slot_start(slot):
        return datetime.fromtimestamp(slot * 300, UTC)

    def _fetch_provider_snapshot(self, now):
        """Fetch once and split the payload into closed history + current 5m bar."""
        try:
            response = self.session.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "symbol": "XAU/USD",
                    "interval": "5min",
                    "outputsize": 2400,
                    "timezone": "UTC",
                    "order": "ASC",
                    "apikey": self.key,
                    "format": "JSON",
                },
                timeout=(5, 25),
            )
        except requests.RequestException:
            raise DataError("market_connection_failed") from None
        if response.status_code != 200:
            _quota_diagnostics(response, "time_series")
            raise DataError(f"market_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise DataError("market_response_not_json") from None
        if isinstance(payload, dict) and payload.get("status") == "error":
            code = payload.get("code")
            raise DataError("market_quota_reached" if code == 429 else "market_provider_error")

        all_bars = parse_bars(payload, now)
        closed = closed_only(all_bars, now)
        require_fresh(closed, now, 600)
        expected = self._slot_start(self._slot(now))
        current = next((bar for bar in all_bars if bar.start == expected), None)
        return closed, current

    def _store_snapshot(self, now, bars, current):
        slot = self._slot(now)
        self._shared_bars = bars
        self._shared_current_bar = current
        self._shared_slot = slot
        self.provider_fetches += 1
        LOG.info(
            "shared_market source=provider slot=%s provider_fetches=%s cache_hits=%s current_5m=%s",
            slot,
            self.provider_fetches,
            self.cache_hits,
            current.start.isoformat() if current else None,
        )
        return bars

    def fetch(self, now):
        slot = self._slot(now)
        if self._shared_bars is not None and self._shared_slot == slot:
            require_fresh(self._shared_bars, now, 600)
            self.cache_hits += 1
            LOG.info(
                "shared_market source=cache slot=%s provider_fetches=%s cache_hits=%s current_5m=%s",
                slot,
                self.provider_fetches,
                self.cache_hits,
                self._shared_current_bar.start.isoformat() if self._shared_current_bar else None,
            )
            return self._shared_bars

        bars, current = self._fetch_provider_snapshot(now)
        return self._store_snapshot(now, bars, current)

    def current_candle_reference(self, now, max_entry_delay_seconds=45):
        """Return the real current 5m candle OPEN only when timing is aligned.

        A quick setup is allowed only during the first ``max_entry_delay_seconds``
        of the slot and only when the provider actually supplied a candle whose
        start timestamp exactly equals that slot's start.  Cached/previous candles
        are never substituted for a new quick entry.
        """
        slot = self._slot(now)
        slot_start = self._slot_start(slot)
        elapsed = now.timestamp() - slot_start.timestamp()
        if elapsed < 0 or elapsed > max_entry_delay_seconds:
            raise DataError("quick_candle_entry_window_missed")

        current = self._shared_current_bar if self._shared_slot == slot else None
        if current is None and self._current_retry_slot != slot:
            # The official cycle can fetch a few seconds before the provider has
            # published the new forming candle.  Permit one same-slot refresh for
            # the quick cycle, never an unlimited retry loop.
            self._current_retry_slot = slot
            bars, current = self._fetch_provider_snapshot(now)
            self._store_snapshot(now, bars, current)

        if current is None or current.start != slot_start:
            raise DataError("quick_current_candle_unavailable")

        return {
            "price": float(current.open),
            "observed_price": float(current.close),
            "time": current.start.timestamp(),
            "candle_start": current.start.timestamp(),
            "candle_start_iso": current.start.isoformat(),
            "observed_at": now.timestamp(),
            "entry_delay_seconds": round(elapsed, 3),
            "source": "Twelve Data - افتتاح شمعة 5د الحالية",
            "delayed_reference": False,
            "shared_candle_reference": True,
            "current_five_minute_candle": True,
            "timing_aligned": True,
        }


def closed_bar_reference(bars, now):
    """Reference monitoring to the latest CLOSED fresh 5m candle.

    This remains useful for continuity monitoring.  New quick entries use
    ``SharedV4Market.current_candle_reference`` instead.
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
