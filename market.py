"""Validated XAU/USD candles. No network operations occur at import time."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

import requests

UTC = timezone.utc


class DataError(RuntimeError):
    pass


def timestamp(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    # The provider request explicitly asks for UTC, including offset-free strings.
    return (dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC))


@dataclass(frozen=True)
class Bar:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    minutes: int = 5

    @property
    def end(self):
        return self.start + timedelta(minutes=self.minutes)


def parse_bars(payload, now, minutes=5):
    if not isinstance(payload, dict) or not isinstance(payload.get("values"), list):
        raise DataError("market_response_invalid")
    if payload.get("status") == "error":
        raise DataError("market_provider_rejected_request")
    meta = payload.get("meta", {})
    if meta.get("symbol", "XAU/USD").upper() != "XAU/USD":
        raise DataError("market_symbol_mismatch")
    by_time = {}
    try:
        for row in payload["values"]:
            dt = timestamp(row["datetime"])
            values = [float(row[k]) for k in ("open", "high", "low", "close")]
            o, h, l, c = values
            if not all(math.isfinite(v) and v > 0 for v in values):
                raise DataError("market_price_not_finite_positive")
            if not l <= min(o, c) <= max(o, c) <= h:
                raise DataError("market_ohlc_invalid")
            if dt > now + timedelta(seconds=5):
                raise DataError("market_timestamp_in_future")
            if dt.timestamp() % (minutes * 60):
                raise DataError("market_timestamp_not_aligned")
            bar = Bar(dt, o, h, l, c, minutes)
            if dt in by_time and by_time[dt] != bar:
                raise DataError("market_conflicting_duplicate")
            by_time[dt] = bar
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise DataError("market_row_invalid") from None
    bars = sorted(by_time.values(), key=lambda b: b.start)
    if not bars:
        raise DataError("market_empty")
    return bars


def closed_only(bars, now, settle_seconds=10):
    return [b for b in bars if b.end <= now - timedelta(seconds=settle_seconds)]


def resample(bars, minutes):
    """Only complete, clock-aligned groups; never bridge missing candles."""
    if minutes not in (15, 60) or any(b.minutes != 5 for b in bars):
        raise ValueError("resampling_requires_five_minute_bars")
    groups = {}
    width = minutes * 60
    for bar in bars:
        bucket = int(bar.start.timestamp()) // width * width
        groups.setdefault(bucket, []).append(bar)
    result = []
    for bucket, group in sorted(groups.items()):
        group.sort(key=lambda b: b.start)
        expected = list(range(bucket, bucket + width, 300))
        if [int(b.start.timestamp()) for b in group] != expected:
            continue
        result.append(Bar(datetime.fromtimestamp(bucket, UTC), group[0].open,
                          max(b.high for b in group), min(b.low for b in group),
                          group[-1].close, minutes))
    return result


def require_fresh(bars, now, max_age_seconds=600):
    if not bars:
        raise DataError("market_no_closed_candles")
    age = (now - bars[-1].end).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise DataError("market_closed_candles_stale")
    return age


class Market:
    def __init__(self, key, session=None):
        self.key = key
        self.session = session or requests.Session()

    def fetch(self, now):
        try:
            response = self.session.get(
                "https://api.twelvedata.com/time_series",
                params={"symbol": "XAU/USD", "interval": "5min", "outputsize": 2400,
                        "timezone": "UTC", "order": "ASC", "apikey": self.key,
                        "format": "JSON"}, timeout=(5, 25))
        except requests.RequestException:
            raise DataError("market_connection_failed") from None
        if response.status_code != 200:
            raise DataError(f"market_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise DataError("market_response_not_json") from None
        if isinstance(payload, dict) and payload.get("status") == "error":
            code = payload.get("code")
            raise DataError("market_quota_reached" if code == 429 else "market_provider_error")
        bars = closed_only(parse_bars(payload, now), now)
        require_fresh(bars, now)
        return bars
