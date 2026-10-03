"""Official U.S. Treasury yield context for Gigi shadow analysis.

Uses Treasury compact XML feeds for nominal and TIPS par yields. This is a slow
opportunity-cost layer, never an intraday entry trigger.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
import urllib.request
import xml.etree.ElementTree as ET

try:
    import requests
except Exception:
    requests = None

NOMINAL_URL = "https://home.treasury.gov/sites/default/files/interest-rates/yield.xml"
REAL_URL = "https://home.treasury.gov/sites/default/files/interest-rates/real_yield.xml"
CACHE_SECONDS = 30 * 60
_cache = {"fetched_at": 0.0, "value": None}


def _local(tag):
    return str(tag).split("}")[-1]


def _to_float(text):
    try:
        return float(str(text).strip())
    except Exception:
        return None


def _parse_date(text):
    raw = str(text or "").strip()
    for fmt in ("%d-%b-%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    raise ValueError("treasury_date_parse_failed")


def parse_records(xml_text, date_tag, field_tags):
    root = ET.fromstring(str(xml_text))
    records = []
    for node in root.iter():
        if _local(node.tag) not in ("G_NEW_DATE", "entry"):
            continue
        values = {}
        for child in node.iter():
            tag = _local(child.tag)
            if tag == date_tag:
                values["date"] = _parse_date(child.text)
            elif tag in field_tags:
                values[tag] = _to_float(child.text)
        if "date" in values and any(values.get(f) is not None for f in field_tags):
            records.append(values)
    # Fallback for flat/simplified XML in tests or feed changes.
    if not records:
        current = {}
        for node in root.iter():
            tag = _local(node.tag)
            if tag == date_tag:
                if current.get("date") is not None:
                    records.append(current)
                    current = {}
                current["date"] = _parse_date(node.text)
            elif tag in field_tags:
                current[tag] = _to_float(node.text)
        if current.get("date") is not None:
            records.append(current)
    records.sort(key=lambda x: x["date"])
    return records


def _change_bps(records, field, periods):
    good = [r for r in records if r.get(field) is not None]
    if len(good) <= periods:
        return None
    return round((float(good[-1][field]) - float(good[-1-periods][field])) * 100.0, 2)


def parse(nominal_xml, real_xml, now=None):
    nominal = parse_records(nominal_xml, "BID_CURVE_DATE", {"BC_2YEAR", "BC_10YEAR"})
    real = parse_records(real_xml, "TIPS_CURVE_DATE", {"TC_10YEAR"})
    if len(nominal) < 2 or len(real) < 2:
        raise ValueError("treasury_history_too_short")

    n = nominal[-1]
    r = real[-1]
    latest_date = min(n["date"], r["date"])
    now_dt = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(float(now), timezone.utc)
    age_days = max(0, (now_dt.date() - latest_date.date()).days)

    real_1d = _change_bps(real, "TC_10YEAR", 1)
    real_5d = _change_bps(real, "TC_10YEAR", 5)
    two_1d = _change_bps(nominal, "BC_2YEAR", 1)
    two_5d = _change_bps(nominal, "BC_2YEAR", 5)
    ten_1d = _change_bps(nominal, "BC_10YEAR", 1)

    if real_5d is None:
        real_regime = "INSUFFICIENT_HISTORY"
    elif real_5d >= 10:
        real_regime = "RISING_REAL_YIELD"
    elif real_5d <= -10:
        real_regime = "FALLING_REAL_YIELD"
    else:
        real_regime = "STABLE_REAL_YIELD"

    if two_5d is None:
        policy_regime = "INSUFFICIENT_HISTORY"
    elif two_5d >= 10:
        policy_regime = "RISING_FRONT_END"
    elif two_5d <= -10:
        policy_regime = "FALLING_FRONT_END"
    else:
        policy_regime = "STABLE_FRONT_END"

    stale = age_days > 7
    if stale:
        real_regime = "STALE"
        policy_regime = "STALE"

    return {
        "as_of": latest_date.date().isoformat(),
        "age_days": age_days,
        "real_history_sessions": len([x for x in real if x.get("TC_10YEAR") is not None]),
        "nominal_history_sessions": len([x for x in nominal if x.get("BC_2YEAR") is not None]),
        "nominal_2y": n.get("BC_2YEAR"),
        "nominal_10y": n.get("BC_10YEAR"),
        "real_10y": r.get("TC_10YEAR"),
        "curve_10y_minus_2y_bps": None if n.get("BC_2YEAR") is None or n.get("BC_10YEAR") is None else round((n["BC_10YEAR"]-n["BC_2YEAR"])*100.0,2),
        "real_10y_change_1d_bps": real_1d,
        "real_10y_change_5d_bps": real_5d,
        "nominal_2y_change_1d_bps": two_1d,
        "nominal_2y_change_5d_bps": two_5d,
        "nominal_10y_change_1d_bps": ten_1d,
        "real_yield_regime": real_regime,
        "policy_regime": policy_regime,
        "source": "US_TREASURY_OFFICIAL_XML",
        "directional_signal": False,
        "note": "opportunity_cost_context_not_entry_signal",
    }


def _get_text(url, session=None):
    headers={"User-Agent":"Laith-Gigi-Treasury/1.0","Accept":"application/xml,text/xml"}
    if session is not None:
        r=session.get(url,timeout=10,headers=headers)
        r.raise_for_status()
        return r.text
    if requests is not None:
        try:
            r=requests.get(url,timeout=10,headers=headers)
            r.raise_for_status()
            return r.text
        except Exception:
            pass
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=10) as res:
        return res.read().decode("utf-8",errors="replace")


def fetch(now=None, session=None):
    now=time.time() if now is None else float(now)
    if _cache["value"] is not None and now-float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])
    try:
        nominal=_get_text(NOMINAL_URL,session=session)
        real=_get_text(REAL_URL,session=session)
        value=parse(nominal,real,now=now)
        value["error"]=None
        _cache.update({"fetched_at":now,"value":value})
        return dict(value)
    except Exception as exc:
        if _cache["value"] is not None:
            value=dict(_cache["value"])
            value["error"]="refresh_failed"
            return value
        return {
            "real_yield_regime":"UNKNOWN",
            "policy_regime":"UNKNOWN",
            "error":type(exc).__name__,
            "source":"US_TREASURY_OFFICIAL_XML",
            "directional_signal":False,
        }
