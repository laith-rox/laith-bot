"""China / India local gold premium context for Gigi shadow analysis.

Uses World Gold Council's public local-premium chart feed. The WGC describes
this as an indicative directional gauge, not a trading metric. Gigi therefore
uses it only as slow physical-demand context and never as an entry trigger.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time

try:
    import requests
except Exception:
    requests = None

URL = "https://fsapi.gold.org/api/v11/charts/local-gold-price-premiums?cache=false20250113"
CACHE_SECONDS = 30 * 60
_cache = {"fetched_at": 0.0, "value": None}


def _percentile(values, value):
    clean = [float(x) for x in values if x is not None]
    if not clean:
        return None
    return sum(x <= float(value) for x in clean) / len(clean)


def _state(value, pct):
    if pct is None:
        return "UNKNOWN"
    value = float(value)
    if value > 0 and pct >= 0.80:
        return "STRONG_PREMIUM"
    if value > 0:
        return "PREMIUM"
    if value < 0 and pct <= 0.20:
        return "STRONG_DISCOUNT"
    if value < 0:
        return "DISCOUNT"
    return "FLAT"


def _parse_series(series):
    rows = [(int(ts), float(v)) for ts, v in (series or []) if v is not None]
    if len(rows) < 30:
        raise ValueError("local_premium_history_too_short")
    ts, latest = rows[-1]
    values_1y = [v for _, v in rows[-252:]]
    pct = _percentile(values_1y, latest)
    change_5 = latest - rows[-6][1] if len(rows) >= 6 else 0.0
    change_20 = latest - rows[-21][1] if len(rows) >= 21 else 0.0
    return {
        "as_of": datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).date().isoformat(),
        "value_usd_oz": round(latest, 3),
        "percentile_1y": None if pct is None else round(pct, 3),
        "change_5d": round(change_5, 3),
        "change_20d": round(change_20, 3),
        "state": _state(latest, pct),
    }


def parse(payload):
    chart = (payload or {}).get("chartData") or {}
    china = _parse_series(chart.get("china_premdisc"))
    india = _parse_series(chart.get("india_premdisc"))
    as_of = str(chart.get("asOfDate") or china["as_of"])
    return {
        "as_of": china["as_of"],
        "chart_as_of": as_of,
        "china": china,
        "india": india,
        "source": "WORLD_GOLD_COUNCIL_LOCAL_PREMIUM_PUBLIC_API",
        "directional_signal": False,
        "note": "indicative_local_demand_context_not_trading_metric",
    }


def fetch(now=None, session=None):
    now = time.time() if now is None else float(now)
    if _cache["value"] is not None and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])
    if requests is None and session is None:
        return {
            "as_of": None,
            "china": {"state": "UNKNOWN"},
            "india": {"state": "UNKNOWN"},
            "error": "requests_unavailable",
            "source": "WORLD_GOLD_COUNCIL_LOCAL_PREMIUM_PUBLIC_API",
            "directional_signal": False,
        }
    session = session or requests
    try:
        r = session.get(
            URL,
            timeout=10,
            headers={
                "User-Agent": "Laith-Gigi-LocalPremium/1.0",
                "Referer": "https://www.gold.org/goldhub/data/gold-premium",
                "Accept": "application/json",
            },
        )
        r.raise_for_status()
        value = parse(r.json())
        value["error"] = None
        _cache.update({"fetched_at": now, "value": value})
        return dict(value)
    except Exception as exc:
        if _cache["value"] is not None:
            value = dict(_cache["value"])
            value["error"] = "refresh_failed"
            return value
        return {
            "as_of": None,
            "china": {"state": "UNKNOWN"},
            "india": {"state": "UNKNOWN"},
            "error": type(exc).__name__,
            "source": "WORLD_GOLD_COUNCIL_LOCAL_PREMIUM_PUBLIC_API",
            "directional_signal": False,
        }
