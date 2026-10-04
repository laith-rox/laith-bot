"""Macro surprise context for Gigi shadow analysis.

Parses actual vs forecast values from the USD calendar and classifies whether a
known data surprise is typically USD-positive or USD-negative. This is context
only. The observed gold reaction can confirm or reject the textbook direction.
"""
from __future__ import annotations

import re


_MULTIPLIERS = {"K":1e3,"M":1e6,"B":1e9,"T":1e12}


def parse_number(value):
    text=str(value or "").strip().upper().replace(",","")
    if not text or "|" in text:
        return None
    text=text.replace("%","")
    m=re.fullmatch(r"([+-]?\d+(?:\.\d+)?)([KMBT]?)",text)
    if not m:
        return None
    number=float(m.group(1))
    suffix=m.group(2)
    return number*_MULTIPLIERS.get(suffix,1.0)


def surprise_polarity(title, event_class):
    """Return +1 when a higher-than-forecast value is usually USD-positive."""
    text=str(title or "").lower()
    cls=str(event_class or "UNKNOWN").upper()

    # Labour exceptions: higher unemployment/claims are usually USD-negative.
    if "unemployment rate" in text or "unemployment claims" in text or "jobless claims" in text:
        return -1
    # Inflation, payrolls, earnings, activity and growth: higher is usually
    # interpreted as more USD-supportive / less dovish, all else equal.
    if cls in (
        "CPI","PCE","PPI","LABOR_NFP","ISM","RETAIL_SALES",
        "GDP","PMI","SENTIMENT","LABOR_OTHER"
    ):
        return 1
    return 0


def event_surprise(event):
    event=event or {}
    actual=parse_number(event.get("actual"))
    forecast=parse_number(event.get("forecast"))
    if actual is None or forecast is None:
        return {
            "status":"UNAVAILABLE",
            "usd_surprise":"UNKNOWN",
            "gold_textbook_pressure":"UNKNOWN",
            "actual":actual,
            "forecast":forecast,
        }
    delta=actual-forecast
    scale=max(abs(forecast),abs(actual),1e-9)
    relative=delta/scale
    polarity=surprise_polarity(event.get("title"),event.get("event_class"))

    if abs(relative) <= 1e-6:
        usd="INLINE"
    elif polarity==0:
        usd="UNMAPPED"
    elif delta*polarity > 0:
        usd="USD_POSITIVE"
    else:
        usd="USD_NEGATIVE"

    if usd=="USD_POSITIVE":
        gold_pressure="BEARISH_TEXTBOOK"
    elif usd=="USD_NEGATIVE":
        gold_pressure="BULLISH_TEXTBOOK"
    elif usd=="INLINE":
        gold_pressure="NEUTRAL"
    else:
        gold_pressure="UNKNOWN"

    return {
        "status":"AVAILABLE",
        "usd_surprise":usd,
        "gold_textbook_pressure":gold_pressure,
        "actual":actual,
        "forecast":forecast,
        "raw_delta":delta,
        "relative_delta":round(relative,6),
        "polarity":polarity,
    }


def analyze(macro, event_response=None):
    macro=macro or {}
    event_response=event_response or {}
    events=list(macro.get("event_bundle") or [])
    if not events:
        active={}
        if macro.get("active_event_title"):
            active={
                "title":macro.get("active_event_title"),
                "event_class":macro.get("active_event_class"),
                "impact":macro.get("active_event_impact"),
                "actual":macro.get("active_event_actual"),
                "forecast":macro.get("active_event_forecast"),
            }
            events=[active]

    parts=[]
    usd_votes=[]
    for event in events:
        result=event_surprise(event)
        parts.append({
            "title":event.get("title"),
            "event_class":event.get("event_class"),
            **result,
        })
        if result["usd_surprise"]=="USD_POSITIVE":
            usd_votes.append(1)
        elif result["usd_surprise"]=="USD_NEGATIVE":
            usd_votes.append(-1)

    if not usd_votes:
        bundle="UNKNOWN"
    elif all(v>0 for v in usd_votes):
        bundle="USD_POSITIVE"
    elif all(v<0 for v in usd_votes):
        bundle="USD_NEGATIVE"
    else:
        bundle="MIXED"

    impulse=str(event_response.get("impulse") or "NONE").upper()
    if bundle=="USD_POSITIVE" and impulse=="BEARISH":
        price_relation="TEXTBOOK_CONFIRMED"
    elif bundle=="USD_NEGATIVE" and impulse=="BULLISH":
        price_relation="TEXTBOOK_CONFIRMED"
    elif bundle=="USD_POSITIVE" and impulse=="BULLISH":
        price_relation="GOLD_REJECTED_USD_POSITIVE_SURPRISE"
    elif bundle=="USD_NEGATIVE" and impulse=="BEARISH":
        price_relation="GOLD_REJECTED_USD_NEGATIVE_SURPRISE"
    elif bundle in ("USD_POSITIVE","USD_NEGATIVE") and impulse=="MUTED":
        price_relation="SURPRISE_MUTED_IN_GOLD"
    else:
        price_relation="UNRESOLVED"

    return {
        "bundle_surprise":bundle,
        "price_relation":price_relation,
        "events":parts[:6],
        "directional_signal":False,
        "note":"macro_surprise_context_not_trade_instruction",
    }
