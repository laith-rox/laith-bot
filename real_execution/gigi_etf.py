"""World Gold Council ETF-flow context for Gigi shadow analysis.

Uses the public Goldhub chart API. ETF flows are a slow allocation/flow layer,
never an intraday entry trigger. Regional breadth is considered so one region
cannot dominate the interpretation unnoticed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time

try:
    import requests
except Exception:
    requests = None

FLOWS_URL = "https://fsapi.gold.org/api/v11/charts/etfv2/revised/flows-chart2"
HOLDINGS_URL = "https://fsapi.gold.org/api/v11/charts/etfv2/revised/holdings-chart2"
CACHE_SECONDS = 30 * 60
REGIONS = ("North America", "Europe", "Asia", "Other")
_cache = {"fetched_at": 0.0, "value": None}


def _series_map(payload, frequency="Weekly", unit="usd"):
    arr = payload["chartData"]["data"][frequency]["series"][unit]
    return {str(item["name"]): item["data"] for item in arr}


def _weekly_total(series_map, index=-1):
    return sum(float(series_map[name][index][1] or 0.0) for name in REGIONS)


def parse(flows_payload, holdings_payload):
    usd = _series_map(flows_payload, "Weekly", "usd")
    tonnes = _series_map(flows_payload, "Weekly", "tonnes")
    if any(name not in usd or name not in tonnes for name in REGIONS):
        raise ValueError("etf_regions_missing")
    if min(len(usd[name]) for name in REGIONS) < 4:
        raise ValueError("etf_weekly_history_too_short")

    ts = int(usd["North America"][-1][0])
    latest_usd = {name: float(usd[name][-1][1] or 0.0) for name in REGIONS}
    latest_t = {name: float(tonnes[name][-1][1] or 0.0) for name in REGIONS}
    total_usd = sum(latest_usd.values())
    total_t = sum(latest_t.values())
    four_week_usd = sum(_weekly_total(usd, -i) for i in range(1, 5))
    positive_regions = sum(v > 0 for v in latest_usd.values())
    negative_regions = sum(v < 0 for v in latest_usd.values())
    major_positive = all(latest_usd[name] > 0 for name in ("North America","Europe","Asia"))
    major_negative = all(latest_usd[name] < 0 for name in ("North America","Europe","Asia"))
    western = latest_usd["North America"] + latest_usd["Europe"]
    asia = latest_usd["Asia"]

    holdings = holdings_payload["chartData"]["data"]["Weekly"]["tonnes"]
    columns = list(holdings["columns"])
    row = list(holdings["set"][-1])
    col = {name: i for i, name in enumerate(columns)}
    if any(name not in col for name in REGIONS):
        raise ValueError("etf_holdings_regions_missing")
    holdings_t = sum(float(row[col[name]] or 0.0) for name in REGIONS)

    if total_usd > 0 and major_positive and four_week_usd > 0:
        regime = "BROAD_INFLOW"
    elif total_usd < 0 and major_negative and four_week_usd < 0:
        regime = "BROAD_OUTFLOW"
    elif four_week_usd > 0 and total_usd > 0:
        regime = "MIXED_INFLOW"
    elif four_week_usd < 0 and total_usd < 0:
        regime = "MIXED_OUTFLOW"
    else:
        regime = "MIXED"

    if western > 0 and asia > 0:
        breadth = "WEST_AND_ASIA_INFLOW"
    elif western < 0 and asia < 0:
        breadth = "WEST_AND_ASIA_OUTFLOW"
    elif western > 0 and asia < 0:
        breadth = "WEST_IN_ASIA_OUT"
    elif western < 0 and asia > 0:
        breadth = "WEST_OUT_ASIA_IN"
    else:
        breadth = "MIXED"

    return {
        "as_of": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat(),
        "weekly_flow_usd": round(total_usd, 2),
        "weekly_flow_tonnes": round(total_t, 4),
        "four_week_flow_usd": round(four_week_usd, 2),
        "holdings_tonnes": round(holdings_t, 2),
        "positive_regions": positive_regions,
        "negative_regions": negative_regions,
        "north_america_usd": round(latest_usd["North America"], 2),
        "europe_usd": round(latest_usd["Europe"], 2),
        "asia_usd": round(latest_usd["Asia"], 2),
        "other_usd": round(latest_usd["Other"], 2),
        "breadth": breadth,
        "regime": regime,
        "source": "WORLD_GOLD_COUNCIL_GOLDHUB_PUBLIC_API",
    }


def fetch(now=None, session=None):
    now = time.time() if now is None else float(now)
    if _cache["value"] is not None and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])
    if requests is None and session is None:
        return {"regime": "UNKNOWN", "error": "requests_unavailable", "source": "WORLD_GOLD_COUNCIL_GOLDHUB_PUBLIC_API"}
    session = session or requests
    headers = {
        "User-Agent": "Laith-Gigi-ETF/1.0",
        "Referer": "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows",
        "Accept": "application/json",
    }
    try:
        f = session.get(FLOWS_URL, timeout=10, headers=headers)
        h = session.get(HOLDINGS_URL, timeout=10, headers=headers)
        f.raise_for_status(); h.raise_for_status()
        value = parse(f.json(), h.json())
        value["error"] = None
        _cache.update({"fetched_at": now, "value": value})
        return dict(value)
    except Exception as exc:
        if _cache["value"] is not None:
            value = dict(_cache["value"])
            value["error"] = "refresh_failed"
            return value
        return {
            "regime": "UNKNOWN",
            "error": type(exc).__name__,
            "source": "WORLD_GOLD_COUNCIL_GOLDHUB_PUBLIC_API",
        }
