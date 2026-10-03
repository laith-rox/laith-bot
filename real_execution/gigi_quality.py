"""External-context data quality for Gigi shadow analysis.

Slow/derived feeds have different publication cadences. This module prevents a
fresh-looking number from being treated as current when its source is stale or
missing. It never places orders and is not an execution gate.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _parse_date(value):
    raw=str(value or "").strip()
    if not raw:
        return None
    formats=(
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw,fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if dt.tzinfo is None:
            dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _age_days(value, now_dt):
    dt=_parse_date(value)
    if dt is None:
        return None
    return max(0.0,(now_dt-dt).total_seconds()/86400.0)


def assess(positioning=None, etf=None, volatility=None, options=None, yields=None, macro=None, now=None, local_premium=None):
    positioning=positioning or {}
    etf=etf or {}
    volatility=volatility or {}
    options=options or {}
    yields=yields or {}
    macro=macro or {}
    local_premium=local_premium or {}
    now_dt=datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(float(now),timezone.utc)

    specs={
        "cftc":(positioning.get("report_date"),10.0,positioning.get("error")),
        "etf":(etf.get("as_of"),10.0,etf.get("error")),
        "gvz":(volatility.get("gvz_date"),5.0,volatility.get("error")),
        "options":(options.get("as_of"),3.5,options.get("error")),
        "yields":(yields.get("as_of"),5.0,yields.get("error")),
        "local_premium":(local_premium.get("as_of"),10.0,local_premium.get("error")),
    }

    ages={}
    stale=[]
    missing=[]
    available=[]
    for name,(date_value,max_age,error) in specs.items():
        age=_age_days(date_value,now_dt)
        ages[name]=None if age is None else round(age,2)
        if error and not date_value:
            missing.append(name)
        elif age is None:
            missing.append(name)
        elif age > max_age:
            stale.append(name)
        else:
            available.append(name)

    macro_regime=str(macro.get("regime") or "UNKNOWN").upper()
    macro_horizon=str(macro.get("calendar_horizon") or "UNKNOWN").upper()
    macro_ok=(
        macro_regime not in ("UNKNOWN","HORIZON_EXHAUSTED")
        and macro_horizon!="EXHAUSTED"
        and not macro.get("calendar_error")
    )
    if macro_ok:
        available.append("macro")
    else:
        missing.append("macro")

    if not stale and len(available)>=7:
        quality="HIGH"
    elif len(available)>=5 and len(stale)<=1:
        quality="MEDIUM"
    else:
        quality="LOW"

    return {
        "quality":quality,
        "available_sources":sorted(set(available)),
        "stale_sources":sorted(set(stale)),
        "missing_sources":sorted(set(missing)),
        "ages_days":ages,
        "note":"source_freshness_context_not_execution_gate",
    }
