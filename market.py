"""Validated XAU/USD candles. No network operations occur at import time."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import math
import threading
import time
import requests

UTC = timezone.utc
LOG = logging.getLogger("laith.market")

_QUOTA_LOCK = threading.Lock()
_QUOTA_BLOCK_UNTIL = 0.0

def _quota_blocked(now=None):
    epoch = time.time() if now is None else float(now)
    with _QUOTA_LOCK:
        return epoch < _QUOTA_BLOCK_UNTIL

def _activate_quota_breaker(response=None):
    """Stop provider traffic after a daily quota rejection until next UTC day + 5m."""
    global _QUOTA_BLOCK_UNTIL
    now = datetime.now(UTC)
    tomorrow = (now + timedelta(days=1)).date()
    reset = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 5, tzinfo=UTC).timestamp()
    with _QUOTA_LOCK:
        _QUOTA_BLOCK_UNTIL = max(_QUOTA_BLOCK_UNTIL, reset)
    LOG.error("twelve_daily_quota_breaker active_until=%s", datetime.fromtimestamp(reset, UTC).isoformat())
    return reset

def _provider_429(response):
    if response is None or response.status_code != 429:
        return False
    _quota_diagnostics(response, "quota_breaker")
    message = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            message = str(payload.get("message") or "").lower()
    except (ValueError, TypeError):
        pass
    # Twelve Data also returns HTTP 429 for the per-minute credit limit. That is
    # temporary and must not trip the daily breaker for the rest of the UTC day.
    minute_limit = (
        "current minute" in message
        or "per minute" in message
        or ("minute" in message and "wait for the next minute" in message)
    )
    if minute_limit:
        LOG.warning("twelve_minute_quota_limit temporary=true")
        return False
    _activate_quota_breaker(response)
    return True

class DataError(RuntimeError):
    pass

def _quota_diagnostics(response, endpoint):
    """Log only non-secret quota metadata for provider throttling diagnostics."""
    if response is None or response.status_code != 429:
        return
    headers = response.headers or {}
    used = headers.get("api-credits-used") or headers.get("Api-Credits-Used")
    left = headers.get("api-credits-left") or headers.get("Api-Credits-Left")
    request = headers.get("api-credits-request") or headers.get("Api-Credits-Request")
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    code = None
    status = None
    message = None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            code = payload.get("code")
            status = payload.get("status")
            raw_message = payload.get("message")
            if raw_message is not None:
                message = str(raw_message).replace("\n", " ")[:240]
    except (ValueError, TypeError):
        pass
    LOG.warning(
        "twelve_quota endpoint=%s http=429 credits_used=%s credits_left=%s credits_request=%s retry_after=%s provider_code=%s provider_status=%s provider_message=%s",
        endpoint, used, left, request, retry_after, code, status, message,
    )

def timestamp(value):
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)

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
            o,h,l,c = values
            if not all(math.isfinite(v) and v > 0 for v in values): raise DataError("market_price_not_finite_positive")
            if not l <= min(o,c) <= max(o,c) <= h: raise DataError("market_ohlc_invalid")
            if dt > now + timedelta(seconds=5): raise DataError("market_timestamp_in_future")
            if dt.timestamp() % (minutes*60): raise DataError("market_timestamp_not_aligned")
            bar=Bar(dt,o,h,l,c,minutes)
            if dt in by_time and by_time[dt] != bar: raise DataError("market_conflicting_duplicate")
            by_time[dt]=bar
    except (ValueError,TypeError,KeyError,OverflowError):
        raise DataError("market_row_invalid") from None
    bars=sorted(by_time.values(),key=lambda b:b.start)
    if not bars: raise DataError("market_empty")
    return bars

def closed_only(bars, now, settle_seconds=10):
    return [b for b in bars if b.end <= now-timedelta(seconds=settle_seconds)]

def resample(bars, minutes):
    if minutes not in (15,60) or any(b.minutes != 5 for b in bars): raise ValueError("resampling_requires_five_minute_bars")
    groups={}; width=minutes*60
    for bar in bars:
        bucket=int(bar.start.timestamp())//width*width; groups.setdefault(bucket,[]).append(bar)
    result=[]
    for bucket,group in sorted(groups.items()):
        group.sort(key=lambda b:b.start); expected=list(range(bucket,bucket+width,300))
        if [int(b.start.timestamp()) for b in group] != expected: continue
        result.append(Bar(datetime.fromtimestamp(bucket,UTC),group[0].open,max(b.high for b in group),min(b.low for b in group),group[-1].close,minutes))
    return result

def require_fresh(bars, now, max_age_seconds=600):
    if not bars: raise DataError("market_no_closed_candles")
    age=(now-bars[-1].end).total_seconds()
    if age < 0 or age > max_age_seconds: raise DataError("market_closed_candles_stale")
    return age

def parse_quote(payload, now):
    """Timestamped provider rate, never a broker executable bid/ask."""
    try:
        if not isinstance(payload, dict) or payload.get('symbol') != 'XAU/USD':
            raise DataError('market_quote_invalid')
        price = float(payload['rate'])
        stamp = float(payload['timestamp'])
        if not math.isfinite(price) or price <= 0 or not math.isfinite(stamp):
            raise DataError('market_quote_invalid')
        if not 0 <= now.timestamp() - stamp <= 90:
            raise DataError('market_quote_stale')
        return {'price': price, 'time': stamp, 'source': 'Twelve Data'}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise DataError('market_quote_invalid') from None

class Market:
    def __init__(self,key,session=None): self.key=key; self.session=session or requests.Session()
    def quote(self, clock):
        if _quota_blocked():
            raise DataError("market_daily_quota_reached")
        try:
            response = self.session.get('https://api.twelvedata.com/exchange_rate',
                params={'symbol':'XAU/USD', 'apikey':self.key}, timeout=(5, 10))
            if response.status_code != 200:
                _quota_diagnostics(response, "exchange_rate")
                if _provider_429(response):
                    raise DataError("market_daily_quota_reached")
                raise DataError('market_quote_unavailable')
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise DataError('market_quote_unavailable') from None
        return parse_quote(payload, clock())
    def fetch(self,now):
        if _quota_blocked():
            raise DataError("market_daily_quota_reached")
        try:
            response=self.session.get("https://api.twelvedata.com/time_series",params={"symbol":"XAU/USD","interval":"5min","outputsize":2400,"timezone":"UTC","order":"ASC","apikey":self.key,"format":"JSON"},timeout=(5,25))
        except requests.RequestException: raise DataError("market_connection_failed") from None
        if response.status_code != 200:
            _quota_diagnostics(response, "time_series")
            if _provider_429(response):
                raise DataError("market_daily_quota_reached")
            raise DataError(f"market_http_{response.status_code}")
        try: payload=response.json()
        except ValueError: raise DataError("market_response_not_json") from None
        if isinstance(payload,dict) and payload.get("status")=="error":
            code=payload.get("code"); raise DataError("market_quota_reached" if code==429 else "market_provider_error")
        bars=closed_only(parse_bars(payload,now),now); require_fresh(bars,now); return bars
