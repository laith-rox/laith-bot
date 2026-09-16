"""Research-only global context for Laith Bot V3.

The module intentionally uses slow-moving public macro series as context, not as
standalone trade signals.  Every historical lookup is as-of safe: by default a
trading decision may only use observations dated strictly before that decision's
calendar date.  This sacrifices some timeliness to avoid accidental look-ahead.

Default public series (FRED graph CSV, no API key required):
- DTWEXBGS: trade-weighted broad U.S. dollar index
- DGS10: 10-year nominal Treasury yield
- DFII10: 10-year real Treasury yield
- VIXCLS: VIX close (risk proxy; copyright remains with Cboe)
- DCOILWTICO: WTI spot oil price

These variables are research features.  They do not prove a causal or stable
relationship with intraday gold returns and must pass out-of-sample tests before
any live use.
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


def parse_fred_csv(text, series_id):
    """Parse one FRED graph CSV series, dropping missing/non-finite observations."""
    rows = []
    reader = csv.DictReader(StringIO(text))
    date_key = "DATE" if "DATE" in (reader.fieldnames or []) else "observation_date"
    if series_id not in (reader.fieldnames or []):
        raise ValueError("fred_series_column_missing")
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


def asof_pair(observations, asof, strict_previous_day=True, lag=5):
    """Return latest and prior observations available at a decision time.

    strict_previous_day=True intentionally excludes same-date daily closes from an
    intraday decision.  It is conservative and prevents using an end-of-day value
    that was not yet observable at the decision timestamp.
    """
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
    """Build a compact as-of-safe macro snapshot from parsed series histories."""
    values, changes, dates = {}, {}, {}
    for name, observations in history.items():
        pair = asof_pair(observations, asof)
        if not pair:
            values[name] = changes[name] = dates[name] = None
            continue
        latest, _ = pair
        values[name] = latest.value
        changes[name] = _change(pair)
        dates[name] = latest.day.isoformat()
    score, parts = gold_macro_score(changes)
    freshness_days = []
    for day_text in dates.values():
        if day_text:
            freshness_days.append((asof.date() - date.fromisoformat(day_text)).days)
    return {
        "asof": asof.astimezone(UTC).isoformat(),
        "values": values,
        "changes_5obs": changes,
        "observation_dates": dates,
        "gold_macro_score": score,
        "gold_macro_parts": parts,
        "max_staleness_days": max(freshness_days) if freshness_days else None,
    }


def gold_macro_score(changes):
    """Transparent directional context score; not a calibrated probability.

    Positive score means the selected slow-moving macro changes are, in aggregate,
    historically more supportive of gold; negative means more headwind.  The score
    is deliberately coarse so research can test it without optimizing many knobs.
    """
    score = 0
    parts = {}

    # Dollar and real yields are treated as the two primary opportunity-cost legs.
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

    # Oil is recorded but intentionally not directional: inflation, yields and
    # geopolitical shocks can make its gold relationship regime-dependent.
    parts["oil_wti"] = 0
    return score, parts


def macro_alignment(side, snapshot):
    """Classify macro context relative to BUY/SELL without fabricating certainty."""
    if side not in ("BUY", "SELL") or not snapshot:
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

    def __init__(self, session=None, refresh_seconds=6 * 3600):
        self.session = session or requests.Session()
        self.refresh_seconds = refresh_seconds
        self.history = {}
        self.fetched_at = 0.0
        self.last_error = None

    def _fetch_series(self, series_id):
        response = self.session.get(
            FRED_CSV,
            params={"id": series_id},
            timeout=(5, 20),
            headers={"User-Agent": "laith-v3-research/1.0"},
        )
        if response.status_code != 200:
            raise RuntimeError("fred_http_error")
        return parse_fred_csv(response.text, series_id)

    def refresh(self, now=None):
        now = now or datetime.now(UTC)
        epoch = now.timestamp()
        if self.history and epoch - self.fetched_at < self.refresh_seconds:
            return
        fresh = {}
        try:
            for name, series_id in SERIES.items():
                fresh[name] = self._fetch_series(series_id)
        except Exception as exc:
            self.last_error = type(exc).__name__ + ":" + str(exc)
            if not self.history:
                raise
            return
        self.history = fresh
        self.fetched_at = time.time()
        self.last_error = None

    def snapshot(self, now):
        self.refresh(now)
        return build_snapshot(self.history, now)
