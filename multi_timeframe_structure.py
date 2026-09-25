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
        return {"side": None, "reason": "mtf_not_enough_rows"}
    h4 = aggregate_h4(h1)
    if len(h4) < 20:
        return {"side": None, "reason": "h4_not_enough_rows"}

    h4c = [r["close"] for r in h4]
    e20, e50 = _ema(h4c,20), _ema(h4c,50)
    slope = e20[-1] - e20[-3]
    h4_up = e20[-1] > e50[-1] and slope > 0
    h4_dn = e20[-1] < e50[-1] and slope < 0
    h4_bias = "UP" if h4_up else ("DOWN" if h4_dn else "NEUTRAL")

    # Important H4 map for context.
    h4_res = max(r["high"] for r in h4[-13:-1])
    h4_sup = min(r["low"] for r in h4[-13:-1])

    # M15 is both the directional and execution structure map. Exclude the two newest closed bars
    # from the level so they can prove a breakout and hold/retest.
    atr15 = max(_atr(m15,14), 0.01)
    zone = max(0.20, 0.12*atr15)
    base = m15[-18:-2]
    resistance = max(r["high"] for r in base)
    support = min(r["low"] for r in base)
    prev, last = m15[-2], m15[-1]
    break_up = prev["close"] > resistance + zone and last["close"] > resistance
    break_dn = prev["close"] < support - zone and last["close"] < support
    retest_up = break_up and last["low"] <= resistance + 0.35*atr15 and last["close"] > resistance
    retest_dn = break_dn and last["high"] >= support - 0.35*atr15 and last["close"] < support

    # M5 confirms that price is actually moving away from the broken zone.
    c5=[r["close"] for r in m5]; e8=_ema(c5,8); e21=_ema(c5,21)
    m5last=m5[-1]
    mom5=c5[-1]-c5[-4]
    m5_buy = c5[-1] > e8[-1] > e21[-1] and mom5 > 0 and m5last["close"] > m5last["open"]
    m5_sell = c5[-1] < e8[-1] < e21[-1] and mom5 < 0 and m5last["close"] < m5last["open"]

    # Do not take a breakout straight into the opposite H4 boundary.
    room_up = h4_res - last["close"]
    room_dn = last["close"] - h4_sup
    blocked_up = h4_dn or (0 < room_up < max(0.75*atr15, zone*2))
    blocked_dn = h4_up or (0 < room_dn < max(0.75*atr15, zone*2))

    side = None; reason = "mtf_wait"
    if break_up and m5_buy and not blocked_up:
        side = "BUY"; reason = "m15_resistance_break_retest" if retest_up else "m15_resistance_break_hold"
    elif break_dn and m5_sell and not blocked_dn:
        side = "SELL"; reason = "m15_support_break_retest" if retest_dn else "m15_support_break_hold"

    return {
        "side": side, "reason": reason, "h4_bias": h4_bias, "m15_bias": m15_bias,\n        "buy_zone_low": buy_zone_low, "buy_zone_high": buy_zone_high,\n        "sell_zone_low": sell_zone_low, "sell_zone_high": sell_zone_high,
        "h4_support": h4_sup, "h4_resistance": h4_res,
        "m15_support": support, "m15_resistance": resistance,
        "m15_atr": atr15, "break_up": break_up, "break_down": break_dn,
        "retest_up": retest_up, "retest_down": retest_dn,
        "m5_confirm_buy": m5_buy, "m5_confirm_sell": m5_sell,
    }
