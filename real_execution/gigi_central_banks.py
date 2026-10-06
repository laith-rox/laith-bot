"""Slow official-sector gold-flow context for Gigi.

Discovers the latest World Gold Council "Central Bank Gold Statistics" article
from recent monthly archives and extracts the reported monthly net flow. This
is delayed structural context, never an intraday entry trigger.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
import time
from urllib.parse import urljoin
import urllib.request

try:
    import requests
except Exception:
    requests = None

BASE = "https://www.gold.org"
CACHE_SECONDS = 6 * 60 * 60
_cache = {"fetched_at": 0.0, "value": None}


def _clean_html(raw):
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", str(raw))
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _archive_urls(now_dt):
    out = []
    year, month = now_dt.year, now_dt.month
    for back in range(0, 4):
        y, m = year, month - back
        while m <= 0:
            y -= 1
            m += 12
        out.append(f"{BASE}/goldhub/gold-focus/{y:04d}/{m:02d}")
    return out


def discover_article(html):
    links = re.findall(
        r'href=["\']([^"\']*central-bank-gold-statistics[^"\']*)["\']',
        str(html),
        flags=re.I,
    )
    links = [urljoin(BASE, unescape(x)) for x in links]
    links = list(dict.fromkeys(links))
    if not links:
        raise ValueError("central_bank_article_missing")
    return links[0]


def parse_article(raw, url=""):
    html = str(raw)
    text = _clean_html(html)

    published = None
    m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', html)
    if m:
        published = m.group(1)

    patterns = [
        r"net buying reported at\s+([\d.]+)t",
        r"bought\s+(?:a\s+)?net\s+([\d.]+)t",
        r"net purchases totalled\s+([\d.]+)t",
        r"official gold reserves increased by a net\s+([\d.]+)t",
        r"net gold purchases[^\d]{0,30}([\d.]+)t",
    ]
    monthly = None
    for pat in patterns:
        mm = re.search(pat, text, flags=re.I)
        if mm:
            monthly = float(mm.group(1))
            break

    # Explicit monthly net selling language, if present.
    sell = re.search(r"net (?:gold )?sales[^\d]{0,30}([\d.]+)t", text, flags=re.I)
    if monthly is None and sell:
        monthly = -float(sell.group(1))

    ytd = None
    ytd_patterns = [
        r"y-t-d[^.]{0,120}?purchases[^\d]{0,25}(?:around\s+|~)?([\d.]+)t",
        r"purchases have totalled[^\d]{0,25}(?:around\s+|~)?([\d.]+)t",
        r"y-t-d reported buying[^\d]{0,25}([\d.]+)t",
    ]
    for pat in ytd_patterns:
        ym = re.search(pat, text, flags=re.I)
        if ym:
            ytd = float(ym.group(1))
            break

    data_to = None
    dm = re.search(r"Data to\s+([0-9]{1,2}\s+[A-Za-z]+\s+20\d{2})", text, flags=re.I)
    if dm:
        data_to = dm.group(1)

    if monthly is None:
        regime = "UNKNOWN"
    elif monthly >= 40:
        regime = "STRONG_NET_BUYING"
    elif monthly >= 10:
        regime = "NET_BUYING"
    elif monthly > 0:
        regime = "MILD_NET_BUYING"
    elif monthly <= -20:
        regime = "STRONG_NET_SELLING"
    elif monthly < 0:
        regime = "NET_SELLING"
    else:
        regime = "FLAT"

    return {
        "regime": regime,
        "monthly_net_tonnes": monthly,
        "ytd_reported_tonnes": ytd,
        "published_date": published,
        "data_to": data_to,
        "article_url": url,
        "source": "WORLD_GOLD_COUNCIL_CENTRAL_BANK_STATISTICS",
        "directional_signal": False,
        "note": "slow_official_sector_context_not_intraday_trigger",
    }


def _get_text(url, session=None):
    headers = {"User-Agent": "Laith-Gigi-CentralBanks/1.0", "Accept": "text/html"}
    if session is not None:
        res = session.get(url, timeout=10, headers=headers)
        res.raise_for_status()
        return res.text
    if requests is not None:
        res = requests.get(url, timeout=10, headers=headers)
        res.raise_for_status()
        return res.text
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as res:
        return res.read().decode("utf-8", errors="replace")


def fetch(now=None, session=None):
    now = time.time() if now is None else float(now)
    if _cache["value"] is not None and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])

    now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
    last_error = None
    for archive in _archive_urls(now_dt):
        try:
            index_html = _get_text(archive, session=session)
            article = discover_article(index_html)
            article_html = _get_text(article, session=session)
            value = parse_article(article_html, article)
            if value["regime"] == "UNKNOWN":
                last_error = "monthly_net_not_parsed"
                continue
            value["error"] = None
            _cache.update({"fetched_at": now, "value": value})
            return dict(value)
        except Exception as exc:
            last_error = type(exc).__name__

    if _cache["value"] is not None:
        value = dict(_cache["value"])
        value["error"] = "refresh_failed"
        return value
    return {
        "regime": "UNKNOWN",
        "monthly_net_tonnes": None,
        "ytd_reported_tonnes": None,
        "error": last_error or "unavailable",
        "source": "WORLD_GOLD_COUNCIL_CENTRAL_BANK_STATISTICS",
        "directional_signal": False,
        "note": "slow_official_sector_context_not_intraday_trigger",
    }
