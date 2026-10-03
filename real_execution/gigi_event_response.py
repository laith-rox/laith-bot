"""High-impact event response context for Gigi shadow analysis.

Measures what price actually did after a scheduled USD event instead of assuming
the macro headline dictates gold direction. The first shock and the later
5-15 minute digestion are kept separate. Shadow only; never an entry trigger.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _epoch(value):
    raw=str(value or "").strip()
    if not raw:
        return None
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def _atr(rows, period=14):
    rows=list(rows or [])
    if len(rows)<2:
        return 0.0
    trs=[]
    start=max(1,len(rows)-period)
    for i in range(start,len(rows)):
        prev=float(rows[i-1]["close"])
        high=float(rows[i]["high"]); low=float(rows[i]["low"])
        trs.append(max(high-low,abs(high-prev),abs(low-prev)))
    return sum(trs)/len(trs) if trs else 0.0


def analyze(m5, macro):
    rows=list(m5 or [])
    macro=macro or {}
    phase=str(macro.get("phase") or "NORMAL").upper()
    near=list(macro.get("near_high") or [])

    if phase=="PRE_HIGH_EVENT":
        return {
            "state":"PRE_EVENT",
            "impulse":"UNKNOWN",
            "event":near[0].get("title") if near else None,
            "directional_signal":False,
        }
    if not near or phase not in ("HIGH_EVENT_SHOCK_0_5M","HIGH_EVENT_DIGESTION_5_15M"):
        return {
            "state":"NO_ACTIVE_HIGH_EVENT",
            "impulse":"NONE",
            "event":None,
            "directional_signal":False,
        }

    event=near[0]
    event_ts=float(event.get("time") or 0.0)
    if event_ts<=0 or len(rows)<20:
        return {
            "state":"INSUFFICIENT_PRICE_HISTORY",
            "impulse":"UNKNOWN",
            "event":event.get("title"),
            "directional_signal":False,
        }

    stamped=[]
    for row in rows:
        ts=_epoch(row.get("datetime"))
        if ts is not None:
            stamped.append((ts,row))
    stamped.sort(key=lambda x:x[0])
    before=[r for ts,r in stamped if ts < event_ts]
    after=[r for ts,r in stamped if event_ts <= ts <= event_ts+15*60]
    if not before or not after:
        return {
            "state":"WAITING_FOR_CLOSED_POST_EVENT_BAR",
            "impulse":"UNKNOWN",
            "event":event.get("title"),
            "directional_signal":False,
        }

    pre_close=float(before[-1]["close"])
    first_close=float(after[0]["close"])
    latest_close=float(after[-1]["close"])
    atr=max(_atr([r for _,r in stamped if _ < event_ts],14),1e-9)
    shock=(first_close-pre_close)/atr
    latest=(latest_close-pre_close)/atr
    shock_abs=abs(shock)

    if shock_abs < 0.25:
        impulse="MUTED"
    else:
        impulse="BULLISH" if shock>0 else "BEARISH"

    if phase=="HIGH_EVENT_SHOCK_0_5M" or len(after)<2:
        state="FIRST_SPIKE_UNTRUSTED"
    elif shock_abs < 0.25:
        state="MUTED_RESPONSE"
    else:
        same_sign=(shock*latest)>0
        retention=(abs(latest)/shock_abs) if shock_abs>0 else 0.0
        if not same_sign or retention<=0.20:
            state="SHOCK_REVERSED"
        elif retention>=0.65:
            state="SHOCK_CONFIRMED"
        else:
            state="SHOCK_PARTIALLY_RETRACED"

    return {
        "state":state,
        "impulse":impulse,
        "event":event.get("title"),
        "event_time":event_ts,
        "post_event_closed_bars":len(after),
        "shock_atr":round(shock,3),
        "latest_move_atr":round(latest,3),
        "directional_signal":False,
        "note":"observed_price_response_not_macro_direction_rule",
    }
