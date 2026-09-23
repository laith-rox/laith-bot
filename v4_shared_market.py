"""V4-only shared XAU/USD market snapshot.

One Twelve Data 5-minute history request is shared by V4 official and quick
analysis inside the same five-minute slot. Closed candles remain the indicator
input. For quick entries, the provider's forming 5m candle is preferred; when
that candle is omitted by time_series, a timestamped live quote from the same
5m slot is allowed as a fallback instead of forcing WAIT.
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
    """Cache one provider snapshot per five-minute UTC slot."""

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

    def _quote_slot_reference(self, now, slot_start):
        """Try /quote because it exposes the 5m bar timestamp and OHLC directly."""
        try:
            response = self.session.get(
                "https://api.twelvedata.com/quote",
                params={
                    "symbol": "XAU/USD",
                    "interval": "5min",
                    "timezone": "UTC",
                    "apikey": self.key,
                    "format": "JSON",
                },
                timeout=(5, 10),
            )
        except requests.RequestException:
            raise DataError("market_quote_unavailable") from None
        if response.status_code != 200:
            _quota_diagnostics(response, "quote")
            raise DataError("market_quote_unavailable")
        try:
            payload = response.json()
        except ValueError:
            raise DataError("market_quote_unavailable") from None
        if not isinstance(payload, dict) or payload.get("status") == "error":
            raise DataError("market_quote_unavailable")
        try:
            stamp = float(payload["timestamp"])
            price = float(payload["close"])
            candle_open = float(payload["open"])
            candle_high = float(payload["high"])
            candle_low = float(payload["low"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise DataError("market_quote_invalid") from None
        # /quote timestamp is the observation/update time, not guaranteed to be
        # the candle-open timestamp. Accept it when it belongs to the current 5m
        # slot instead of requiring exact equality with the slot boundary.
        slot_end = slot_start.timestamp() + 300
        if stamp < slot_start.timestamp() or stamp >= slot_end or stamp > now.timestamp() + 5:
            raise DataError("quick_quote_not_current_5m_slot")
        if now.timestamp() - stamp > 90:
            raise DataError("quick_quote_stale")
        if not (candle_low <= min(candle_open, price) <= max(candle_open, price) <= candle_high):
            raise DataError("market_quote_ohlc_invalid")
        return {
            "price": price,
            "candle_open": candle_open,
            "candle_high": candle_high,
            "candle_low": candle_low,
            "time": stamp,
            "candle_start": slot_start.timestamp(),
            "candle_start_iso": slot_start.isoformat(),
            "observed_at": stamp,
            "entry_delay_seconds": round(max(0.0, stamp - slot_start.timestamp()), 3),
            "source": "Twelve Data /quote - شمعة 5د الحالية",
            "delayed_reference": False,
            "shared_candle_reference": False,
            "current_five_minute_candle": True,
            "timing_aligned": True,
            "candle_open_estimated": False,
            "candle_open_source": "افتتاح شمعة 5د من /quote",
        }

    def _live_quote_slot_reference(self, now, slot_start, elapsed):
        """Fallback to exchange_rate only when its own timestamp is in this slot."""
        if not self._shared_bars:
            raise DataError("quick_current_candle_unavailable")
        quote = self.quote(lambda: now)
        quote_stamp = float(quote["time"])
        if quote_stamp < slot_start.timestamp() or quote_stamp > now.timestamp() + 5:
            raise DataError("quick_live_quote_not_in_current_slot")
        if now.timestamp() - quote_stamp > 90:
            raise DataError("quick_live_quote_stale")
        previous_close = float(self._shared_bars[-1].close)
        price = float(quote["price"])
        LOG.warning(
            "quick_current_candle_fallback source=live_quote slot_start=%s quote_time=%s previous_close_proxy=%.2f",
            slot_start.isoformat(), datetime.fromtimestamp(quote_stamp, UTC).isoformat(), previous_close,
        )
        return {
            "price": price,
            "candle_open": previous_close,
            "candle_high": max(previous_close, price),
            "candle_low": min(previous_close, price),
            "time": quote_stamp,
            "candle_start": slot_start.timestamp(),
            "candle_start_iso": slot_start.isoformat(),
            "observed_at": quote_stamp,
            "entry_delay_seconds": round(max(0.0, quote_stamp - slot_start.timestamp()), 3),
            "source": "Twelve Data live quote — نفس دورة 5د",
            "delayed_reference": False,
            "shared_candle_reference": False,
            "current_five_minute_candle": True,
            "timing_aligned": True,
            "candle_open_estimated": True,
            "candle_open_source": "إغلاق آخر شمعة 5د مغلقة كمرجع افتتاح احتياطي",
        }

    def current_candle_reference(self, now, max_entry_delay_seconds=300):
        """Return a current-slot 5m reference for a quick candidate.

        The actual forming 5m candle is preferred. If time_series has not exposed
        it yet, a fresh exchange-rate quote is accepted only when the quote's own
        timestamp falls inside the current 5m slot. The prior closed 5m close is
        used transparently as an opening reference in that fallback case.
        """
        slot = self._slot(now)
        slot_start = self._slot_start(slot)
        elapsed = now.timestamp() - slot_start.timestamp()
        if elapsed < 0:
            raise DataError("quick_candle_entry_window_missed")
        # Quick entries are allowed throughout the active 5m slot. Freshness is
        # determined by the provider observation timestamp, not by proximity to
        # the candle boundary.
        if elapsed > max_entry_delay_seconds:
            max_entry_delay_seconds = 300

        current = self._shared_current_bar if self._shared_slot == slot else None
        # Do not immediately repeat time_series inside the same slot when the
        # provider omitted the forming candle. That duplicate request was adding
        # quota pressure without improving the reference in production.
        if current is None and self._current_retry_slot != slot:
            self._current_retry_slot = slot
            LOG.info("quick_current_candle_retry_skipped reason=provider_omits_forming_bar slot=%s", slot)

        if current is None or current.start != slot_start:
            try:
                return self._quote_slot_reference(now, slot_start)
            except DataError as exc:
                LOG.warning("quick_current_candle_quote_fallback_failed reason=%s", exc)
            return self._live_quote_slot_reference(now, slot_start, elapsed)

        return {
            "price": float(current.close),
            "candle_open": float(current.open),
            "candle_high": float(current.high),
            "candle_low": float(current.low),
            "time": now.timestamp(),
            "candle_start": current.start.timestamp(),
            "candle_start_iso": current.start.isoformat(),
            "observed_at": now.timestamp(),
            "entry_delay_seconds": round(elapsed, 3),
            "source": "Twelve Data - شمعة 5د الحالية",
            "delayed_reference": False,
            "shared_candle_reference": True,
            "current_five_minute_candle": True,
            "timing_aligned": True,
            "candle_open_estimated": False,
            "candle_open_source": "افتتاح شمعة 5د من time_series",
        }


def closed_bar_reference(bars, now):
    """Reference monitoring to the latest CLOSED fresh 5m candle."""
    require_fresh(bars, now, 600)
    last = bars[-1]
    return {
        "price": float(last.close),
        "time": last.end.timestamp(),
        "source": "آخر شمعة 5د مغلقة - بيانات V4 المشتركة",
        "delayed_reference": False,
        "shared_candle_reference": True,
    }
