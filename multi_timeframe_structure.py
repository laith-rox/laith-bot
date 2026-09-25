"""Multi-timeframe XAU structure analysis for DEMO signals.

H4 defines the larger regime, M15 defines support/resistance and breakout/hold,
and M5 confirms the entry. Pure logic: no network or broker actions.
"""
from datetime import datetime, timezone


def _ema(values, period):
    if not values:
        return []
    a = 2.0 / (period + 1.0)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(a * float(v) + (1.0 - a) * out[-1])
    return out


def _atr(rows, period=14):
    if len(rows) < 2:
        return 0.0
    out = []
    for i in range(max(1, len(rows)-period), len(rows)):
        p = rows[i-1]["close"]; r = rows[i]
        out.append(max(r["high"]-r["low"], abs(r["high"]-p), abs(r["low"]-p)))
    return sum(out)/len(out) if out else 0.0


def aggregate_h4(h1_rows):
    buckets = {}
    for r in h1_rows:
        try:
            dt = datetime.fromisoformat(str(r["datetime"]).replace("Z","+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        key = dt.replace(hour=(dt.hour//4)*4, minute=0, second=0, microsecond=0)
        b = buckets.setdefault(key, {"datetime": key.isoformat(), "open": r["open"],
                                     "high": r["high"], "low": r["low"], "close": r["close"], "n": 0})
        b["high"] = max(b["high"], r["high"]); b["low"] = min(b["low"], r["low"])
        b["close"] = r["close"]; b["n"] += 1
    # Only completed four-hour proxy candles are used.
    return [{k:v for k,v in b.items() if k!="n"} for _,b in sorted(buckets.items()) if b["n"] == 4]


def analyze_structure(m5, m15, h1):
    if len(m5) < 30 or len(m15) < 35 or len(h1) < 90:
        return {
        "side": side, "reason": reason, "h4_bias": h4_bias, "m15_bias": m15_bias,
        "buy_zone_low": buy_zone_low, "buy_zone_high": buy_zone_high,
        "sell_zone_low": sell_zone_low, "sell_zone_high": sell_zone_high,
        "h4_support": h4_sup, "h4_resistance": h4_res,
        "m15_support": support, "m15_resistance": resistance,
        "m15_atr": atr15, "break_up": break_up, "break_down": break_dn,
        "retest_up": retest_up, "retest_down": retest_dn,
        "m5_confirm_buy": m5_buy, "m5_confirm_sell": m5_sell,
    }
