"""Research-only global context for Laith Bot V3.

Slow-moving public macro series are context, never standalone trade signals.
Historical lookups are as-of safe: intraday decisions use observations dated no
later than the prior calendar day to avoid accidental end-of-day look-ahead.

Default public series (FRED graph CSV, no API key required):
- DTWEXBGS: trade-weighted broad U.S. dollar index
- DGS10: 10-year nominal Treasury yield
- DFII10: 10-year real Treasury yield
- VIXCLS: VIX close (risk proxy; copyright remains with Cboe)
- DCOILWTICO: WTI spot oil price
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

SERIES = {
    "usd_broad": "DTWEXBGS",
    "nominal_10y": "DGS10",
    "real_10y": "DFII10",
    "vix": "VIXCLS",
    "oil_wti": "DCOILWTICO",
}
PRIMARY = ("usd_broad", "real_10y")


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
    """Parse one FRED graph CSV series, dropping missing/non-finite observations."""
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
    """Parse a multi-series FRED CSV and tolerate individually missing series."""
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


def asof_pair(observations, asof, strict_previous_day=True, lag=5):
    """Return latest and prior observations available at a decision time."""
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


def build_snapshot(history, asof):
    """Build a compact as-of-safe macro snapshot from parsed histories."""
    values, changes, dates = {}, {}, {}
    for name in SERIES:
        observations = history.get(name, [])
        pair = asof_pair(observations, asof)
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
    freshness_days = [
        (asof.date() - date.fromisoformat(day_text)).days
        for day_text in dates.values() if day_text
    ]
    return {
        "asof": asof.astimezone(UTC).isoformat(),
        "values": values,
        "changes_5obs": changes,
        "observation_dates": dates,
        "gold_macro_score": score,
        "gold_macro_parts": parts,
        "coverage": coverage,
        "primary_coverage": primary_coverage,
        "max_staleness_days": max(freshness_days) if freshness_days else None,
    }


def gold_macro_score(changes):
    """Transparent directional context score; not a calibrated probability."""
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


def macro_alignment(side, snapshot):
    """Classify macro context relative to BUY/SELL without fabricating certainty."""
    if side not in ("BUY", "SELL") or not snapshot:
        return "UNAVAILABLE"
    # Do not let one surviving series create a false strong macro vote.
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
    """Low-frequency cached public macro context for the paper research worker."""

    def __init__(self, session=None, refresh_seconds=6 * 3600, history_days=180):
        self.session = session or requests.Session()
        self.refresh_seconds = refresh_seconds
        self.history_days = history_days
        self.history = {}
        self.fetched_at = 0.0
        self.last_error = None

    def _params(self, now, ids):
        return {
            "id": ",".join(ids),
            "cosd": (now.date() - timedelta(days=self.history_days)).isoformat(),
            "coed": now.date().isoformat(),
        }

    def _request(self, now, ids, timeout=(5, 15)):
        response = self.session.get(
            FRED_CSV,
            params=self._params(now, ids),
            timeout=timeout,
            headers={"User-Agent": "laith-v3-research/1.1"},
        )
        if response.status_code != 200:
            raise RuntimeError("fred_http_" + str(response.status_code))
        return response.text

    def _fetch_bundle(self, now):
        text = self._request(now, list(SERIES.values()))
        return parse_fred_bundle(text)

    def _fetch_fallback(self, now):
        """Fallback to small single-series requests; keep any successful series."""
        fresh = {}
        errors = []
        for name, series_id in SERIES.items():
            try:
                text = self._request(now, [series_id], timeout=(4, 10))
                fresh[name] = parse_fred_csv(text, series_id)
            except Exception as exc:
                errors.append(name + ":" + type(exc).__name__ + ":" + str(exc))
        if not fresh:
            raise RuntimeError("fred_all_series_failed:" + "|".join(errors))
        return fresh, errors

    def refresh(self, now=None):
        now = now or datetime.now(UTC)
        epoch = now.timestamp()
        if self.history and epoch - self.fetched_at < self.refresh_seconds:
            return
        errors = []
        try:
            fresh = self._fetch_bundle(now)
        except Exception as exc:
            errors.append("bundle:" + type(exc).__name__ + ":" + str(exc))
            try:
                fresh, fallback_errors = self._fetch_fallback(now)
                errors.extend(fallback_errors)
            except Exception as fallback_exc:
                errors.append("fallback:" + type(fallback_exc).__name__ + ":" + str(fallback_exc))
                self.last_error = "|".join(errors)
                if not self.history:
                    raise RuntimeError(self.last_error) from fallback_exc
                return
        self.history = fresh
        self.fetched_at = time.time()
        self.last_error = "|".join(errors) if errors else None

    def snapshot(self, now):
        self.refresh(now)
        return build_snapshot(self.history, now)
