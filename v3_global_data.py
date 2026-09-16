"""Research-only global context for Laith Bot V3.

Slow-moving public macro/market series are context, never standalone trade
signals. Historical lookups are as-of safe: intraday decisions use observations
dated no later than the prior calendar day to avoid accidental end-of-day
look-ahead.

Primary source: FRED daily series.
Runtime fallback: low-frequency Twelve Data daily market proxies, following the
same general macro-proxy approach used by Twelve Data's public world-model
research dataset (for example UUP as a dollar proxy, TLT as a rates proxy, and
VIXY as a volatility proxy).  Proxy data is explicitly labelled and is never
silently presented as the official economic series.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
import csv
import math
import time

import requests

UTC = timezone.utc
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TWELVE_TIME_SERIES = "https://api.twelvedata.com/time_series"

SERIES = {
    "usd_broad": "DTWEXBGS",
    "nominal_10y": "DGS10",
    "real_10y": "DFII10",
    "vix": "VIXCLS",
    "oil_wti": "DCOILWTICO",
}
PRIMARY = ("usd_broad", "real_10y")

PROXY_SERIES = {
    "usd_proxy": "UUP",
    "bond_proxy": "TLT",
    "vol_proxy": "VIXY",
    "equity_proxy": "SPY",
    "oil_proxy": "USO",
}
PROXY_PRIMARY = ("usd_proxy", "bond_proxy")


@dataclass(frozen=True)
class Observation:
    day: date
    value: float


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _date_key(fieldnames):
    fields = fieldnames or []
    if "DATE" in fields:
        return "DATE"
    if "observation_date" in fields:
        return "observation_date"
    raise ValueError("fred_date_column_missing")


def parse_fred_csv(text, series_id):
    reader = csv.DictReader(StringIO(text))
    date_key = _date_key(reader.fieldnames)
    if series_id not in (reader.fieldnames or []):
        raise ValueError("fred_series_column_missing")
    rows = []
    for row in reader:
        try:
            day = date.fromisoformat(row[date_key])
        except (KeyError, TypeError, ValueError):
            continue
        value = _finite(row.get(series_id))
        if value is not None:
            rows.append(Observation(day, value))
    if not rows:
        raise ValueError("fred_series_empty")
    rows.sort(key=lambda item: item.day)
    return rows


def parse_fred_bundle(text):
    reader = csv.DictReader(StringIO(text))
    date_key = _date_key(reader.fieldnames)
    available = set(reader.fieldnames or [])
    reverse = {series_id: name for name, series_id in SERIES.items() if series_id in available}
    if not reverse:
        raise ValueError("fred_bundle_series_missing")
    histories = {name: [] for name in SERIES}
    for row in reader:
        try:
            day = date.fromisoformat(row[date_key])
        except (KeyError, TypeError, ValueError):
            continue
        for series_id, name in reverse.items():
            value = _finite(row.get(series_id))
            if value is not None:
                histories[name].append(Observation(day, value))
    return {name: rows for name, rows in histories.items() if rows}


def parse_twelve_bundle(payload):
    """Parse a batched Twelve Data /time_series response into proxy histories."""
    if not isinstance(payload, dict):
        raise ValueError("twelve_proxy_invalid")
    reverse = {symbol: name for name, symbol in PROXY_SERIES.items()}
    histories = {}
    for symbol, name in reverse.items():
        item = payload.get(symbol)
        # Defensive support for a single-symbol-shaped response in tests/manual use.
        if item is None and payload.get("meta", {}).get("symbol") == symbol:
            item = payload
        if not isinstance(item, dict) or item.get("status") == "error":
            continue
        values = item.get("values")
        if not isinstance(values, list):
            continue
        rows = []
        for row in values:
            try:
                day = date.fromisoformat(str(row["datetime"])[:10])
            except (KeyError, TypeError, ValueError):
                continue
            value = _finite(row.get("close"))
            if value is not None and value > 0:
                rows.append(Observation(day, value))
        rows.sort(key=lambda obs: obs.day)
        if rows:
            histories[name] = rows
    if not histories:
        raise ValueError("twelve_proxy_empty")
    return histories


def asof_pair(observations, asof, strict_previous_day=True, lag=5):
    cutoff = asof.date() - timedelta(days=1 if strict_previous_day else 0)
    eligible = [item for item in observations if item.day <= cutoff]
    if not eligible:
        return None
    latest = eligible[-1]
    prior = eligible[max(0, len(eligible) - 1 - lag)]
    return latest, prior


def _change(pair):
    if not pair:
        return None
    latest, prior = pair
    return latest.value - prior.value


def _return(pair):
    if not pair:
        return None
    latest, prior = pair
    if prior.value <= 0:
        return None
    return latest.value / prior.value - 1.0


def _freshness(dates, asof):
    days = [
        (asof.date() - date.fromisoformat(day_text)).days
        for day_text in dates.values() if day_text
    ]
    return max(days) if days else None


def build_snapshot(history, asof):
    """Build an as-of-safe snapshot from official-style daily macro histories."""
    values, changes, dates = {}, {}, {}
    for name in SERIES:
        pair = asof_pair(history.get(name, []), asof)
        if not pair:
            values[name] = changes[name] = dates[name] = None
            continue
        latest, _ = pair
        values[name] = latest.value
        changes[name] = _change(pair)
        dates[name] = latest.day.isoformat()
    score, parts = gold_macro_score(changes)
    coverage = sum(changes.get(name) is not None for name in SERIES)
    primary_coverage = sum(changes.get(name) is not None for name in PRIMARY)
    return {
        "source": "fred",
        "asof": asof.astimezone(UTC).isoformat(),
        "values": values,
        "changes_5obs": changes,
        "observation_dates": dates,
        "gold_macro_score": score,
        "gold_macro_parts": parts,
        "coverage": coverage,
        "primary_coverage": primary_coverage,
        "max_staleness_days": _freshness(dates, asof),
    }


def build_proxy_snapshot(history, asof):
    """Build an as-of-safe snapshot from explicitly labelled market proxies."""
    values, returns, dates = {}, {}, {}
    for name in PROXY_SERIES:
        pair = asof_pair(history.get(name, []), asof)
        if not pair:
            values[name] = returns[name] = dates[name] = None
            continue
        latest, _ = pair
        values[name] = latest.value
        returns[name] = _return(pair)
        dates[name] = latest.day.isoformat()
    score, parts = gold_proxy_score(returns)
    coverage = sum(returns.get(name) is not None for name in PROXY_SERIES)
    primary_coverage = sum(returns.get(name) is not None for name in PROXY_PRIMARY)
    return {
        "source": "twelve_proxy",
        "asof": asof.astimezone(UTC).isoformat(),
        "values": values,
        "returns_5obs": returns,
        "observation_dates": dates,
        "gold_macro_score": score,
        "gold_macro_parts": parts,
        "coverage": coverage,
        "primary_coverage": primary_coverage,
        "max_staleness_days": _freshness(dates, asof),
    }


def gold_macro_score(changes):
    """Coarse context score for official-style daily changes, not probability."""
    score = 0
    parts = {}
    for key, weight, invert in (
        ("usd_broad", 2, True),
        ("real_10y", 2, True),
        ("nominal_10y", 1, True),
        ("vix", 1, False),
    ):
        change = changes.get(key)
        if change is None or abs(change) < 1e-12:
            parts[key] = 0
            continue
        sign = 1 if change > 0 else -1
        contribution = -weight * sign if invert else weight * sign
        parts[key] = contribution
        score += contribution
    parts["oil_wti"] = 0
    return score, parts


def gold_proxy_score(returns):
    """Coarse market-proxy score; deliberately simple and separately labelled.

    UUP rising is treated as a dollar headwind. TLT rising is treated as a bond-
    price/rates-tailwind proxy. VIXY rising is a weak risk-aversion tailwind.
    SPY and USO are recorded for later research but have no directional vote in
    v1 because their relationship with gold is regime-dependent.
    """
    score = 0
    parts = {}
    for key, weight, invert in (
        ("usd_proxy", 2, True),
        ("bond_proxy", 2, False),
        ("vol_proxy", 1, False),
    ):
        change = returns.get(key)
        if change is None or abs(change) < 1e-12:
            parts[key] = 0
            continue
        sign = 1 if change > 0 else -1
        contribution = -weight * sign if invert else weight * sign
        parts[key] = contribution
        score += contribution
    parts["equity_proxy"] = 0
    parts["oil_proxy"] = 0
    return score, parts


def macro_alignment(side, snapshot):
    if side not in ("BUY", "SELL") or not snapshot:
        return "UNAVAILABLE"
    if snapshot.get("primary_coverage", 0) < 2 or snapshot.get("coverage", 0) < 3:
        return "UNAVAILABLE"
    score = snapshot.get("gold_macro_score")
    if not isinstance(score, (int, float)):
        return "UNAVAILABLE"
    directional = score if side == "BUY" else -score
    if directional >= 4:
        return "STRONG_ALIGN"
    if directional >= 1:
        return "ALIGN"
    if directional <= -4:
        return "STRONG_CONFLICT"
    if directional <= -1:
        return "CONFLICT"
    return "NEUTRAL"


class GlobalContextProvider:
    """Cached FRED context with a low-credit Twelve market-proxy fallback."""

    def __init__(self, session=None, refresh_seconds=6 * 3600, history_days=180, twelve_key=None):
        self.session = session or requests.Session()
        self.refresh_seconds = refresh_seconds
        self.history_days = history_days
        self.twelve_key = twelve_key
        self.history = {}
        self.source = None
        self.fetched_at = 0.0
        self.last_error = None

    def _fred_params(self, now, ids):
        return {
            "id": ",".join(ids),
            "cosd": (now.date() - timedelta(days=self.history_days)).isoformat(),
            "coed": now.date().isoformat(),
        }

    def _fred_request(self, now, ids, timeout=(4, 6)):
        response = self.session.get(
            FRED_CSV,
            params=self._fred_params(now, ids),
            timeout=timeout,
            headers={"User-Agent": "laith-v3-research/1.2"},
        )
        if response.status_code != 200:
            raise RuntimeError("fred_http_" + str(response.status_code))
        return response.text

    def _fetch_fred_bundle(self, now):
        return parse_fred_bundle(self._fred_request(now, list(SERIES.values())))

    def _fetch_fred_sequential(self, now):
        fresh, errors = {}, []
        for name, series_id in SERIES.items():
            try:
                fresh[name] = parse_fred_csv(self._fred_request(now, [series_id]), series_id)
            except Exception as exc:
                errors.append(name + ":" + type(exc).__name__ + ":" + str(exc))
        if not fresh:
            raise RuntimeError("fred_all_series_failed:" + "|".join(errors))
        return fresh, errors

    def _fetch_twelve_proxy(self):
        if not self.twelve_key:
            raise RuntimeError("twelve_proxy_key_missing")
        response = self.session.get(
            TWELVE_TIME_SERIES,
            params={
                "symbol": ",".join(PROXY_SERIES.values()),
                "interval": "1day",
                "outputsize": 15,
                "order": "ASC",
                "timezone": "UTC",
                "apikey": self.twelve_key,
                "format": "JSON",
            },
            timeout=(5, 20),
        )
        if response.status_code != 200:
            raise RuntimeError("twelve_proxy_http_" + str(response.status_code))
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError("twelve_proxy_not_json") from None
        if payload.get("status") == "error":
            raise RuntimeError("twelve_proxy_provider_error")
        return parse_twelve_bundle(payload)

    def refresh(self, now=None):
        now = now or datetime.now(UTC)
        epoch = now.timestamp()
        if self.history and epoch - self.fetched_at < self.refresh_seconds:
            return
        errors = []
        try:
            fresh = self._fetch_fred_bundle(now)
            source = "fred"
        except Exception as exc:
            errors.append("fred_bundle:" + type(exc).__name__ + ":" + str(exc))
            if self.twelve_key:
                try:
                    fresh = self._fetch_twelve_proxy()
                    source = "twelve_proxy"
                except Exception as proxy_exc:
                    errors.append("twelve_proxy:" + type(proxy_exc).__name__ + ":" + str(proxy_exc))
                    fresh = None
            else:
                fresh = None
            if fresh is None:
                try:
                    fresh, fallback_errors = self._fetch_fred_sequential(now)
                    source = "fred"
                    errors.extend(fallback_errors)
                except Exception as fallback_exc:
                    errors.append("fred_fallback:" + type(fallback_exc).__name__ + ":" + str(fallback_exc))
                    self.last_error = "|".join(errors)
                    if not self.history:
                        raise RuntimeError(self.last_error) from fallback_exc
                    return
        self.history = fresh
        self.source = source
        self.fetched_at = time.time()
        self.last_error = "|".join(errors) if errors else None

    def snapshot(self, now):
        self.refresh(now)
        if self.source == "twelve_proxy":
            return build_proxy_snapshot(self.history, now)
        return build_snapshot(self.history, now)
