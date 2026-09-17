"""V4-only shared market cache to reduce Twelve Data credit usage.

This module is intentionally isolated from the old bot and V3. One XAU/USD
5-minute history request is shared by V4 official, quick, and H4 analysis inside
the same five-minute slot. Trading rules are not changed here.
"""
from datetime import datetime, timezone
import logging

from market import Bar, DataError, Market, require_fresh, timestamp

UTC = timezone.utc
LOG = logging.getLogger("laith.v4.market")


class SharedV4Market(Market):
    """Cache one successful 5m history fetch per five-minute UTC slot."""

    def __init__(self, key, session=None):
        super().__init__(key, session=session)
        self._shared_bars = None
        self._shared_slot = None
        self._shared_current = None
        self.provider_fetches = 0
        self.cache_hits = 0
        self._current_retry_slot = None

    @staticmethod
    def _slot(now):
        return int(now.timestamp() // 300)

    @staticmethod
    def _slot_start(now):
        return datetime.fromtimestamp(int(now.timestamp() // 300) * 300, tz=UTC)

    def _fetch_provider_snapshot(self, now):
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
        except Exception:
            raise DataError("market_connection_failed") from None
        if response.status_code != 200:
            raise DataError(f"market_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise DataError("market_response_not_json") from None
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise DataError("market_provider_error")
        values = payload.get("values") if isinstance(payload, dict) else None
        if not isinstance(values, list) or not values:
            raise DataError("market_missing_values")

        slot_start = self._slot_start(now)
        parsed = []
        for row in values:
            try:
                start = timestamp(row["datetime"])
                parsed.append(Bar(
                    start,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    5,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        if not parsed:
            raise DataError("market_missing_values")
        parsed.sort(key=lambda bar: bar.start)
        closed = [bar for bar in parsed if bar.start < slot_start]
        current = next((bar for bar in reversed(parsed) if bar.start == slot_start), None)
        if not closed:
            raise DataError("market_missing_closed_values")
        require_fresh(closed, now, 600)
        return closed, current

    def _load_provider_snapshot(self, now):
        bars, current = self._fetch_provider_snapshot(now)
        self._shared_bars = bars
        self._shared_current = current
        self._shared_slot = self._slot(now)
        self.provider_fetches += 1
        LOG.info(
            "shared_market source=provider slot=%s provider_fetches=%s cache_hits=%s current_5m=%s",
            self._shared_slot, self.provider_fetches, self.cache_hits,
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
                slot, self.provider_fetches, self.cache_hits,
                self._shared_current.start.isoformat() if self._shared_current else None,
            )
            return self._shared_bars
        try:
            return self._load_provider_snapshot(now)
        except DataError as exc:
            if self._shared_bars is not None:
                try:
                    require_fresh(self._shared_bars, now, 600)
                    LOG.warning("quick_market_fallback reason=%s source=recent_cached_5m_bars", exc)
                    return self._shared_bars
                except DataError:
                    pass
            raise

    def _live_quote_slot_reference(self, now, slot_start):
        """Fallback to a live quote whose provider timestamp belongs to this slot."""
        if not self._shared_bars:
            raise DataError("quick_current_candle_unavailable")
        quote = self.quote(lambda: now)
        quote_stamp = float(quote["time"])
        if quote_stamp < slot_start.timestamp():
            raise DataError("quick_live_quote_not_in_current_slot")
        previous_close = float(self._shared_bars[-1].close)
        price = float(quote["price"])
        LOG.warning(
            "quick_current_candle_fallback source=live_quote slot_start=%s quote_time=%s previous_close_proxy=%.2f",
            slot_start.isoformat(), datetime.fromtimestamp(quote_stamp, tz=UTC).isoformat(), previous_close,
        )
        return {
            "price": price,
            "candle_open": previous_close,
            "time": quote_stamp,
            "source": "سعر حي داخل شمعة 5د الحالية - بيانات V4 المشتركة",
            "delayed_reference": False,
            "shared_candle_reference": True,
            "forming_candle_reference": True,
            "live_quote_fallback": True,
        }

    def current_candle_reference(self, now, max_entry_delay_seconds=60):
        """Use the current forming 5m candle only near its open.

        Twelve Data can briefly omit the forming candle just after a slot starts.
        In that case retry the time-series snapshot once for the slot before using
        a genuinely fresh quote from the same slot. Stale quotes still fail closed.
        """
        slot_start = self._slot_start(now)
        elapsed = max(0.0, (now - slot_start).total_seconds())
        if elapsed > float(max_entry_delay_seconds):
            raise DataError("quick_candle_entry_window_missed")

        if self._shared_slot != self._slot(now) or self._shared_bars is None:
            self.fetch(now)

        current = self._shared_current
        if current is None and self._current_retry_slot != self._slot(now):
            self._current_retry_slot = self._slot(now)
            try:
                self._load_provider_snapshot(now)
            except DataError as exc:
                LOG.warning("quick_current_candle_retry_failed reason=%s", exc)
            current = self._shared_current

        if current is None:
            # The quote endpoint may lag even when the time-series endpoint is
            # about to publish the forming candle. Give time-series one final
            # refresh before asking quote(); this preserves all stale-data guards.
            try:
                self._load_provider_snapshot(now)
            except DataError as exc:
                LOG.warning("quick_current_candle_final_refresh_failed reason=%s", exc)
            current = self._shared_current

        if current is None:
            return self._live_quote_slot_reference(now, slot_start)
        return {
            "price": float(current.close),
            "candle_open": float(current.open),
            "time": current.start.timestamp(),
            "source": "شمعة 5د الحالية - بيانات V4 المشتركة",
            "delayed_reference": False,
            "shared_candle_reference": True,
            "forming_candle_reference": True,
        }


def closed_bar_reference(bars, now):
    """Reference monitoring to the latest closed fresh 5m candle."""
    require_fresh(bars, now, 600)
    last = bars[-1]
    return {
        "price": float(last.close),
        "time": last.end.timestamp(),
        "source": "آخر شمعة 5د مغلقة - بيانات V4 المشتركة",
        "delayed_reference": False,
        "shared_candle_reference": True,
    }
