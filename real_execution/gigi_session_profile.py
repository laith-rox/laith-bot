"""Broker-native session / VWAP-proxy context for Gigi shadow analysis.

Uses closed MT5 M5 candles. VWAP is weighted by broker tick volume, which is a
proxy for activity rather than centralized exchange volume. London and New York
session anchors are DST-aware through IANA timezones.

This module never places orders and does not create a directional signal.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except Exception:  # pragma: no cover
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

UTC = timezone.utc
try:
    LONDON = ZoneInfo("Europe/London") if ZoneInfo is not None else UTC
    NEW_YORK = ZoneInfo("America/New_York") if ZoneInfo is not None else UTC
    TZ_SOURCE = "IANA"
except ZoneInfoNotFoundError:  # pragma: no cover
    LONDON = UTC
    NEW_YORK = UTC
    TZ_SOURCE = "UTC_FALLBACK"


def _dt(row):
    raw=str((row or {}).get("datetime") or "").strip()
    if not raw:
        raise ValueError("bar_datetime_missing")
    value=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if value.tzinfo is None:
        value=value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _atr(rows, period=14):
    if len(rows) < 2:
        return 0.0
    trs=[]
    start=max(1,len(rows)-period)
    for i in range(start,len(rows)):
        prev=float(rows[i-1]["close"])
        high=float(rows[i]["high"])
        low=float(rows[i]["low"])
        trs.append(max(high-low,abs(high-prev),abs(low-prev)))
    return sum(trs)/len(trs) if trs else 0.0


def _vwap(rows):
    num=0.0
    den=0.0
    for row in rows:
        typical=(float(row["high"])+float(row["low"])+float(row["close"]))/3.0
        try:
            weight=float(row.get("tick_volume") or 0.0)
        except Exception:
            weight=0.0
        if weight <= 0:
            weight=1.0
        num += typical*weight
        den += weight
    return (num/den) if den > 0 else None


def _window(rows, tz, day, start_minute, end_minute):
    out=[]
    for row in rows:
        local=_dt(row).astimezone(tz)
        minute=local.hour*60+local.minute
        if local.date()==day and start_minute <= minute < end_minute:
            out.append(row)
    return out


def _since(rows, tz, day, start_minute):
    out=[]
    for row in rows:
        local=_dt(row).astimezone(tz)
        minute=local.hour*60+local.minute
        if local.date()==day and minute >= start_minute:
            out.append(row)
    return out


def _range(rows):
    if not rows:
        return None,None
    return (
        max(float(row["high"]) for row in rows),
        min(float(row["low"]) for row in rows),
    )


def _vwap_relation(rows, vwap):
    if vwap is None or len(rows) < 3:
        return "UNKNOWN"
    closes=[float(row["close"]) for row in rows[-3:]]
    if all(value > vwap for value in closes):
        return "ABOVE_ACCEPTANCE"
    if all(value < vwap for value in closes):
        return "BELOW_ACCEPTANCE"
    return "CROSSING"


def _range_state(last, high, low):
    if high is None or low is None:
        return "UNKNOWN"
    bar_high=float(last["high"])
    bar_low=float(last["low"])
    close=float(last["close"])
    if bar_high > high and close < high:
        return "FAILED_BREAK_ABOVE"
    if bar_low < low and close > low:
        return "FAILED_BREAK_BELOW"
    if close > high:
        return "ACCEPTED_ABOVE"
    if close < low:
        return "ACCEPTED_BELOW"
    return "INSIDE"


def analyze(m5):
    rows=sorted(list(m5 or []), key=_dt)
    if len(rows) < 18:
        return {
            "session":"UNKNOWN",
            "vwap_anchor":"NONE",
            "vwap_relation":"UNKNOWN",
            "extension_state":"UNKNOWN",
            "range_event":"UNKNOWN",
            "data_quality":"INSUFFICIENT",
            "directional_signal":False,
            "volume_note":"broker_tick_volume_proxy_not_centralized_volume",
        }

    latest=rows[-1]
    latest_utc=_dt(latest)
    london_now=latest_utc.astimezone(LONDON)
    ny_now=latest_utc.astimezone(NEW_YORK)
    london_min=london_now.hour*60+london_now.minute
    ny_min=ny_now.hour*60+ny_now.minute

    overnight=_window(rows,LONDON,london_now.date(),0,8*60)
    london_or=_window(rows,LONDON,london_now.date(),8*60,9*60)
    ny_or=_window(rows,NEW_YORK,ny_now.date(),8*60+20,9*60+20)

    overnight_high,overnight_low=_range(overnight)
    london_high,london_low=_range(london_or)
    ny_high,ny_low=_range(ny_or)

    london_anchor=_since(rows,LONDON,london_now.date(),8*60)
    ny_anchor=_since(rows,NEW_YORK,ny_now.date(),8*60+20)

    if ny_min >= 8*60+20 and ny_anchor:
        session="NEW_YORK"
        anchor_name="NEW_YORK_0820"
        anchor_rows=ny_anchor
        active_or=(ny_high,ny_low)
        active_or_complete=ny_min >= 9*60+20
    elif london_min >= 8*60 and london_anchor:
        session="LONDON"
        anchor_name="LONDON_0800"
        anchor_rows=london_anchor
        active_or=(london_high,london_low)
        active_or_complete=london_min >= 9*60
    else:
        session="PRE_LONDON"
        anchor_name="NONE"
        anchor_rows=[]
        active_or=(None,None)
        active_or_complete=False

    anchor_vwap=_vwap(anchor_rows) if anchor_rows else None
    relation=_vwap_relation(anchor_rows,anchor_vwap)
    atr=max(_atr(rows,14),1e-9)
    close=float(latest["close"])
    distance_atr=None if anchor_vwap is None else (close-anchor_vwap)/atr
    if distance_atr is None:
        extension="UNKNOWN"
    elif abs(distance_atr) >= 1.50:
        extension="EXTENDED"
    elif abs(distance_atr) >= 0.75:
        extension="MODERATE"
    else:
        extension="FAIR_VALUE_ZONE"

    overnight_complete=london_min >= 8*60
    overnight_state=(
        _range_state(latest,overnight_high,overnight_low)
        if overnight_complete else "BUILDING"
    )
    opening_state=(
        _range_state(latest,active_or[0],active_or[1])
        if active_or_complete else "BUILDING"
    )

    if active_or_complete:
        range_event=opening_state
    elif overnight_complete:
        range_event=overnight_state
    else:
        range_event="BUILDING"

    expected_history = len(rows) >= 180
    quality="FULL" if expected_history and (overnight or session=="PRE_LONDON") else "PARTIAL"

    return {
        "session":session,
        "vwap_anchor":anchor_name,
        "vwap":None if anchor_vwap is None else round(anchor_vwap,5),
        "vwap_relation":relation,
        "vwap_distance_atr":None if distance_atr is None else round(distance_atr,3),
        "extension_state":extension,
        "overnight_high":None if overnight_high is None else round(overnight_high,5),
        "overnight_low":None if overnight_low is None else round(overnight_low,5),
        "overnight_state":overnight_state,
        "opening_range_high":None if active_or[0] is None else round(active_or[0],5),
        "opening_range_low":None if active_or[1] is None else round(active_or[1],5),
        "opening_range_state":opening_state,
        "range_event":range_event,
        "london_local":london_now.isoformat(),
        "new_york_local":ny_now.isoformat(),
        "timezone_source":TZ_SOURCE,
        "data_quality":quality,
        "directional_signal":False,
        "volume_note":"broker_tick_volume_proxy_not_centralized_volume",
        "note":"session_context_not_entry_signal",
    }
