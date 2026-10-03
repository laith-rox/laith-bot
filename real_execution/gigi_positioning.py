"""Weekly COMEX gold positioning context for Gigi shadow analysis.

Reads the public CFTC disaggregated futures-only report. This is a slow context
layer, never an entry trigger. It helps distinguish trend participation from
crowding/deleveraging.
"""
from __future__ import annotations

from html import unescape
import re
import time
import urllib.request

CFTC_URL = "https://www.cftc.gov/dea/futures/other_lf.htm"
CACHE_SECONDS = 15 * 60
_cache = {"fetched_at": 0.0, "value": None, "error": None}


def _num(text):
    return int(str(text).replace(",", "").replace(":", "").strip())


def parse_gold_report(raw):
    text = unescape(re.sub(r"<[^>]+>", "", str(raw)))
    start = text.find("GOLD - COMMODITY EXCHANGE INC.")
    if start < 0:
        raise ValueError("gold_section_missing")
    end = text.find("MICRO GOLD - COMMODITY EXCHANGE INC.", start + 1)
    block = text[start:end if end > start else None]

    date_match = re.search(
        r"Disaggregated Commitments of Traders - Futures Only,\s*([^\n\r]+)",
        block,
    )
    pos_match = re.search(
        r"All\s*:\s*([\d,]+)\s*:\s*"
        r"([\d,\-]+)\s+([\d,\-]+)\s+"
        r"([\d,\-]+)\s+([\d,\-]+)\s+([\d,\-]+)\s+"
        r"([\d,\-]+)\s+([\d,\-]+)\s+([\d,\-]+)\s+"
        r"([\d,\-]+)\s+([\d,\-]+)\s+([\d,\-]+)",
        block,
    )
    chg_match = re.search(
        r"Changes in Commitments from:[^\n\r]*[\n\r]+\s*:\s*([\d,\-]+)\s*:\s*"
        r"([\d,\-]+)\s+([\d,\-]+)\s+"
        r"([\d,\-]+)\s+([\d,\-]+)\s+([\d,\-]+)\s+"
        r"([\d,\-]+)\s+([\d,\-]+)\s+([\d,\-]+)\s+"
        r"([\d,\-]+)\s+([\d,\-]+)\s+([\d,\-]+)",
        block,
    )
    if not pos_match or not chg_match:
        raise ValueError("gold_position_rows_missing")

    p = [_num(x) for x in pos_match.groups()]
    c = [_num(x) for x in chg_match.groups()]
    oi = p[0]
    mm_long, mm_short, mm_spread = p[6], p[7], p[8]
    other_long, other_short = p[9], p[10]
    mm_net = mm_long - mm_short
    other_net = other_long - other_short
    mm_change = c[6] - c[7]
    other_change = c[9] - c[10]
    mm_net_oi = (mm_net / oi) if oi else 0.0

    if mm_net_oi >= 0.30:
        crowding = "ELEVATED_LONG"
    elif mm_net_oi <= -0.15:
        crowding = "ELEVATED_SHORT"
    else:
        crowding = "NORMAL"

    if mm_net > 0 and mm_change > 0:
        regime = "LONG_BIASED_ADDING"
    elif mm_net > 0 and mm_change < 0:
        regime = "LONG_BIASED_DELEVERAGING"
    elif mm_net < 0 and mm_change < 0:
        regime = "SHORT_BIASED_ADDING"
    elif mm_net < 0 and mm_change > 0:
        regime = "SHORT_BIASED_COVERING"
    else:
        regime = "NEUTRAL"

    return {
        "report_date": date_match.group(1).strip() if date_match else "UNKNOWN",
        "open_interest": oi,
        "managed_money_long": mm_long,
        "managed_money_short": mm_short,
        "managed_money_spreading": mm_spread,
        "managed_money_net": mm_net,
        "managed_money_net_change": mm_change,
        "managed_money_net_oi": round(mm_net_oi, 4),
        "other_reportables_net": other_net,
        "other_reportables_net_change": other_change,
        "crowding": crowding,
        "regime": regime,
        "source": "CFTC_DISAGGREGATED_FUTURES_ONLY",
    }


def fetch(now=None, opener=None):
    now = time.time() if now is None else float(now)
    if _cache["value"] is not None and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])
    opener = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(
            CFTC_URL,
            headers={"User-Agent": "Laith-Gigi-CFTC/1.0", "Accept": "text/html"},
        )
        with opener(req, timeout=8) as res:
            raw = res.read().decode("utf-8", errors="replace")
        value = parse_gold_report(raw)
        value["error"] = None
        _cache.update({"fetched_at": now, "value": value, "error": None})
        return dict(value)
    except Exception as exc:
        if _cache["value"] is not None:
            value = dict(_cache["value"])
            value["error"] = "refresh_failed"
            return value
        return {
            "regime": "UNKNOWN",
            "crowding": "UNKNOWN",
            "error": type(exc).__name__,
            "source": "CFTC_DISAGGREGATED_FUTURES_ONLY",
        }
