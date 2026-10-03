"""GLD options-skew / open-interest context for Gigi shadow analysis.

Uses the public Cboe delayed GLD option-chain feed. This is a proxy for gold
options positioning, not CME COMEX futures options. It is delayed, slow context
and never an entry trigger.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import time
import urllib.request

try:
    import requests
except Exception:
    requests = None

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json"
CACHE_SECONDS = 15 * 60
_cache = {"fetched_at": 0.0, "value": None}


def _parse_contract(symbol):
    text = str(symbol or "")
    if len(text) < 18 or not text.startswith("GLD"):
        raise ValueError("invalid_gld_option_symbol")
    expiry = datetime.strptime(text[3:9], "%y%m%d").replace(tzinfo=timezone.utc)
    cp = text[9]
    strike = int(text[10:18]) / 1000.0
    if cp not in ("C", "P"):
        raise ValueError("invalid_gld_option_type")
    return expiry, cp, strike


def _pick_expiry(options, now_dt):
    counts = {}
    for item in options:
        try:
            expiry, _, _ = _parse_contract(item.get("option"))
        except Exception:
            continue
        dte = (expiry.date() - now_dt.date()).days
        if 7 <= dte <= 45:
            counts[expiry] = counts.get(expiry, 0) + 1
    if not counts:
        raise ValueError("no_usable_option_expiry")
    return min(counts, key=lambda dt: (abs((dt.date()-now_dt.date()).days - 30), -counts[dt]))


def _closest_delta(items, target):
    good = []
    for item in items:
        try:
            iv = float(item.get("iv") or 0.0)
            delta = float(item.get("delta"))
            if iv > 0 and math.isfinite(iv) and math.isfinite(delta):
                good.append(item)
        except Exception:
            continue
    if not good:
        raise ValueError("delta_bucket_empty")
    return min(good, key=lambda x: abs(float(x.get("delta")) - target))


def parse(payload):
    data = payload.get("data") or {}
    options = data.get("options") or []
    spot = float(data.get("current_price") or 0.0)
    if spot <= 0 or not options:
        raise ValueError("option_chain_missing")

    snapshot_time = str(payload.get("timestamp") or "")
    market_time = str(data.get("last_trade_time") or snapshot_time or "")
    try:
        now_dt = datetime.fromisoformat((snapshot_time or market_time).replace("Z", "+00:00"))
    except Exception:
        now_dt = datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    expiry = _pick_expiry(options, now_dt)
    selected = []
    for item in options:
        try:
            exp, cp, strike = _parse_contract(item.get("option"))
        except Exception:
            continue
        if exp.date() == expiry.date():
            row = dict(item)
            row["_cp"] = cp
            row["_strike"] = strike
            selected.append(row)

    calls = [x for x in selected if x["_cp"] == "C"]
    puts = [x for x in selected if x["_cp"] == "P"]
    call25 = _closest_delta(calls, 0.25)
    put25 = _closest_delta(puts, -0.25)
    call25_iv = float(call25["iv"])
    put25_iv = float(put25["iv"])
    rr25 = put25_iv - call25_iv

    band = [x for x in selected if 0.80*spot <= x["_strike"] <= 1.20*spot]
    call_oi = sum(float(x.get("open_interest") or 0.0) for x in band if x["_cp"] == "C")
    put_oi = sum(float(x.get("open_interest") or 0.0) for x in band if x["_cp"] == "P")
    call_vol = sum(float(x.get("volume") or 0.0) for x in band if x["_cp"] == "C")
    put_vol = sum(float(x.get("volume") or 0.0) for x in band if x["_cp"] == "P")
    oi_ratio = (put_oi / call_oi) if call_oi > 0 else None
    vol_ratio = (put_vol / call_vol) if call_vol > 0 else None

    # Gross gamma-open-interest concentration. This is intentionally unsigned:
    # public option-chain data does not reveal dealer positioning sign, so Gigi
    # must not call this "dealer gamma" or infer support/resistance from it.
    gamma_by_strike = {}
    for x in band:
        try:
            gamma = abs(float(x.get("gamma") or 0.0))
            oi = float(x.get("open_interest") or 0.0)
            gamma_by_strike[x["_strike"]] = gamma_by_strike.get(x["_strike"], 0.0) + gamma * oi
        except Exception:
            continue
    gross_gamma_oi = sum(gamma_by_strike.values())
    if gamma_by_strike and gross_gamma_oi > 0:
        top_gamma_strike, top_gamma_value = max(gamma_by_strike.items(), key=lambda kv: kv[1])
        top_gamma_share = top_gamma_value / gross_gamma_oi
        near_gamma = sum(v for strike, v in gamma_by_strike.items() if abs(strike / spot - 1.0) <= 0.02)
        near_gamma_share = near_gamma / gross_gamma_oi
    else:
        top_gamma_strike = None
        top_gamma_share = 0.0
        near_gamma_share = 0.0

    if near_gamma_share >= 0.35:
        gamma_context = "HIGH_NEAR_SPOT_CONVEXITY"
    elif near_gamma_share >= 0.20:
        gamma_context = "MODERATE_NEAR_SPOT_CONVEXITY"
    else:
        gamma_context = "DISTRIBUTED_CONVEXITY"

    if rr25 >= 0.03:
        skew = "DOWNSIDE_HEDGE_BID"
    elif rr25 <= -0.03:
        skew = "UPSIDE_CALL_BID"
    else:
        skew = "BALANCED"

    if oi_ratio is None:
        oi_state = "UNKNOWN"
    elif oi_ratio >= 1.50:
        oi_state = "PUT_HEAVY"
    elif oi_ratio <= 0.67:
        oi_state = "CALL_HEAVY"
    else:
        oi_state = "BALANCED"

    return {
        "as_of": market_time,
        "snapshot_time": snapshot_time,
        "spot": round(spot, 3),
        "expiry": expiry.date().isoformat(),
        "dte": (expiry.date() - now_dt.date()).days,
        "call25_strike": call25["_strike"],
        "call25_delta": round(float(call25["delta"]), 4),
        "call25_iv": round(call25_iv, 4),
        "put25_strike": put25["_strike"],
        "put25_delta": round(float(put25["delta"]), 4),
        "put25_iv": round(put25_iv, 4),
        "rr25_put_minus_call": round(rr25, 4),
        "skew": skew,
        "put_call_oi_ratio": None if oi_ratio is None else round(oi_ratio, 3),
        "put_call_volume_ratio": None if vol_ratio is None else round(vol_ratio, 3),
        "oi_state": oi_state,
        "iv30": data.get("iv30"),
        "gross_gamma_oi_context": gamma_context,
        "near_spot_gamma_share": round(near_gamma_share, 3),
        "top_gamma_strike": None if top_gamma_strike is None else round(float(top_gamma_strike), 3),
        "top_gamma_share": round(float(top_gamma_share), 3),
        "gamma_note": "unsigned_gross_gamma_oi_no_dealer_sign_inference",
        "source": "CBOE_DELAYED_GLD_OPTIONS_PROXY",
        "proxy_note": "GLD_options_not_COMEX_gold_futures_options",
        "directional_signal": False,
    }


def _get_json(url, headers, session=None):
    if session is not None:
        r = session.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        return r.json()
    if requests is not None:
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
        return r.json()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch(now=None, session=None):
    now = time.time() if now is None else float(now)
    if _cache["value"] is not None and now - float(_cache["fetched_at"] or 0) <= CACHE_SECONDS:
        return dict(_cache["value"])
    try:
        payload = _get_json(URL, {"User-Agent":"Laith-Gigi-Options/1.0"}, session=session)
        value = parse(payload)
        value["error"] = None
        _cache.update({"fetched_at": now, "value": value})
        return dict(value)
    except Exception as exc:
        if _cache["value"] is not None:
            value = dict(_cache["value"])
            value["error"] = "refresh_failed"
            return value
        return {
            "skew":"UNKNOWN",
            "oi_state":"UNKNOWN",
            "error":type(exc).__name__,
            "source":"CBOE_DELAYED_GLD_OPTIONS_PROXY",
            "directional_signal":False,
        }
