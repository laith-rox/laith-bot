"""Adaptive market-context and execution review for V4 paper signals (features 11–20).

Never claims synthetic H4 candles are native. Uses only *closed* supplied 5m
bars for derived M15/H1, with explicit provenance. Broker spread unavailable
from Twelve Data's XAU/USD reference price: never invent it.

All diagnostics are heuristics; no calibrated win probabilities or broker orders.
"""
from collections import defaultdict
from datetime import timezone
from zoneinfo import ZoneInfo
import math

from market import resample
from v3_research import session_label

HEBRON = ZoneInfo("Asia/Hebron")
UTC = timezone.utc


def number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _candle(bar, origin):
    if bar is None:
        return {"available": False, "origin": origin}
    opening, closing = number(bar.open), number(bar.close)
    high, low = number(bar.high), number(bar.low)
    if None in (opening, closing, high, low) or high < max(opening, closing) or low > min(opening, closing):
        return {"available": False, "origin": origin}
    span = max(high-low, 1e-9)
    body = abs(closing-opening) / span
    upper = (high - max(opening, closing)) / span
    lower = (min(opening, closing)-low) / span
    return {
        "available": True, "origin": origin,
        "start": bar.start.isoformat(), "end": bar.end.isoformat(),
        "direction": "BUY" if closing > opening else "SELL" if closing < opening else "FLAT",
        "body_fraction": round(body, 3),
        "upper_wick_fraction": round(upper, 3), "lower_wick_fraction": round(lower, 3),
        "upper_rejection": upper >= 0.55,
        "lower_rejection": lower >= 0.55,
    }


def timeframe_candles(bars, native_h4=None):
    """Do not resample H4: native H4 is unavailable unless provided explicitly."""
    closed = [b for b in (bars or []) if getattr(b, "minutes", None) == 5]
    m15 = resample(closed, 15) if closed else []
    h1 = resample(closed, 60) if closed else []
    h4 = (native_h4[-1] if native_h4 and getattr(native_h4[-1], "minutes", None) == 240
          else None)
    return {
        "M5": _candle(closed[-1] if closed else None, "CLOSED_NATIVE_5M"),
        "M15": _candle(m15[-1] if m15 else None, "DERIVED_FROM_COMPLETE_5M"),
        "H1": _candle(h1[-1] if h1 else None, "DERIVED_FROM_COMPLETE_5M"),
        "H4": _candle(h4, "NATIVE_H4_ONLY" if h4 else "NATIVE_H4_UNAVAILABLE"),
        "h4_original_verified": h4 is not None,
    }


def _atr5(bars):
    if len(bars or []) < 16:
        return None
    window = bars[-15:]
    ranges = []
    for prev, current in zip(window, window[1:]):
        ranges.append(max(float(current.high)-float(current.low),
                          abs(float(current.high)-float(prev.close)),
                          abs(float(current.low)-float(prev.close))))
    return sum(ranges)/len(ranges) if ranges else None


def market_character(bars):
    """Regime features based on 5m closes; volatility is not direction."""
    if len(bars or []) < 32:
        return {"state": "UNAVAILABLE", "reason": "insufficient_closed_5m_bars"}
    recent = bars[-32:]
    closes = [float(b.close) for b in recent]
    atr = _atr5(bars)
    if atr is None or atr <= 0:
        return {"state": "UNAVAILABLE", "reason": "insufficient_atr"}
    now_average = sum(closes[-8:])/8
    past_average = sum(closes[-24:-16])/8
    displacement = (now_average-past_average)/atr
    wide = (max(b.high for b in recent[-8:])-min(b.low for b in recent[-8:]))/atr
    last_range = (recent[-1].high-recent[-1].low)/atr
    if last_range >= 2.8:
        state = "VOLATILE_SPIKE"
    elif displacement > 1.2 and wide > 1.2:
        state = "UPTREND"
    elif displacement < -1.2 and wide > 1.2:
        state = "DOWNTREND"
    else:
        state = "RANGE"
    return {"state": state, "source": "closed_5m_heuristic",
            "displacement_atr": round(displacement, 2), "last_range_atr": round(last_range, 2),
            "atr5": round(atr, 4)}


def day_levels(bars, now):
    """Local day, prior local day and completed Asia range, with coverage flags."""
    rows = defaultdict(list)
    for bar in bars or []:
        rows[bar.start.astimezone(HEBRON).date()].append(bar)
    today = now.astimezone(HEBRON).date()
    today_rows = rows.get(today, [])
    previous_days = sorted((d for d in rows if d < today), reverse=True)
    prev_day = previous_days[0] if previous_days else None
    prev = rows.get(prev_day, []) if prev_day else []
    asia = [bar for bar in today_rows if 0 <= bar.start.astimezone(HEBRON).hour < 8]

    def level(data, minimum):
        if len(data) < minimum:
            return {"available": False, "bars": len(data), "coverage": "INSUFFICIENT"}
        return {"available": True, "high": round(max(float(b.high) for b in data), 2),
                "low": round(min(float(b.low) for b in data), 2),
                "bars": len(data), "coverage": "PARTIAL" if len(data) < 200 else "SUBSTANTIAL"}

    return {
        "timezone": "Asia/Hebron",
        "today": {"date": str(today), **level(today_rows, 1)},
        "previous": {"date": str(prev_day) if prev_day else None, **level(prev, 100)},
        "asia": level(asia, 12),
        "disclaimer": "OHLC ranges reflect only provider candles actually returned",
    }


def classify_correction(decision, candles):
    context = (decision.get("context") or {}).get("trend")
    h1 = candles["H1"]
    m15 = candles["M15"]
    quick = decision.get("side")
    if context not in ("BUY", "SELL") or not m15.get("available"):
        return {"state": "UNCERTAIN", "reason": "higher_trend_or_m15_unavailable"}
    if quick in ("BUY", "SELL") and quick != context:
        if h1.get("available") and h1.get("direction") == quick and m15.get("direction") == quick:
            return {"state": "REVERSAL_WATCH", "reason": "m15_h1_against_higher_trend",
                    "confirmed_reversal": False}
        return {"state": "COUNTERTREND_CORRECTION", "reason": "5m_against_higher_trend"}
    if m15.get("direction") != context:
        return {"state": "CORRECTION_WATCH", "reason": "m15_against_higher_trend"}
    return {"state": "ALIGNED", "reason": "m15_with_higher_trend"}


def breakout_confirmation(bars):
    """Closed-candle confirmation, distinct from a mere high/low pierce."""
    if len(bars or []) < 26:
        return {"state": "UNAVAILABLE"}
    older, prev, last = bars[-26:-2], bars[-2], bars[-1]
    resistance = max(float(b.high) for b in older)
    support = min(float(b.low) for b in older)
    if prev.close > resistance and last.close > resistance:
        return {"state": "CONFIRMED_UP", "level": round(resistance, 2),
                "retest": bool(last.low <= resistance and last.close > resistance)}
    if prev.close < support and last.close < support:
        return {"state": "CONFIRMED_DOWN", "level": round(support, 2),
                "retest": bool(last.high >= support and last.close < support)}
    if last.high > resistance and last.close <= resistance:
        return {"state": "UPPER_WICK_REJECTION", "level": round(resistance, 2)}
    if last.low < support and last.close >= support:
        return {"state": "LOWER_WICK_REJECTION", "level": round(support, 2)}
    if last.close > resistance or last.close < support:
        return {"state": "AWAIT_SECOND_CLOSE"}
    return {"state": "NO_CONFIRMED_BREAK"}


def market_adaptation(decision, bars, now, native_h4=None):
    """Features 11–16 use closed bars only and never add provider calls."""
    candles = timeframe_candles(bars, native_h4=native_h4)
    return {
        "version": "v4-adaptive-11-20-v1",
        "feature_11_regime": market_character(bars),
        "feature_12_timeframes": candles,
        "feature_13_session": {"name": session_label(now), "timezone_source": "IANA_DST"},
        "feature_14_levels": day_levels(bars, now),
        "feature_15_correction": classify_correction(decision, candles),
        "feature_16_breakout": breakout_confirmation(bars),
        "status": "RESEARCH_OBSERVATIONS_NOT_PROFIT_FORECAST",
    }


def risk_targets(decision, setup):
    """Feature 18 suggests, but never silently changes, existing paper SL/TP."""
    price = number(setup.get("entry"))
    sl = number(setup.get("stop"))
    target = number(setup.get("target"))
    atr = number(decision.get("atr"))
    side = setup.get("side")
    research = decision.get("v4") or {}
    structural = number((research.get("structural_risk") or {}).get("stop"))
    if None in (price, sl, target) or side not in ("BUY", "SELL"):
        return {"available": False}
    direction = 1 if side == "BUY" else -1
    risk = direction * (price-sl)
    if risk <= 0:
        return {"available": False}
    structural_valid = (
        structural is not None and 0 < direction*(price-structural) <= risk
    )
    resistance = number((research.get("nearest_resistance") or {}).get("low"))
    support = number((research.get("nearest_support") or {}).get("high"))
    opposing = resistance if side == "BUY" else support
    first_target = None
    if opposing is not None and 0 < direction*(opposing-price) < direction*(target-price):
        first_target = opposing
    return {
        "available": True, "mode": "ADVISORY_ONLY",
        "original_stop": sl, "original_target": target,
        "structure_stop_candidate": round(structural, 2) if structural_valid else None,
        "nearby_opposing_target": round(first_target, 2) if first_target is not None else None,
        "risk_price_units": round(risk, 3),
        "atr_price_units": round(atr, 3) if atr is not None else None,
        "no_widening_of_existing_stop": True,
        "no_order_adjustment": True,
    }


def execution_cost(setup, reference):
    """Feature 20: real spread ONLY if reference has verifiable bid and ask."""
    bid, ask = number(reference.get("bid")), number(reference.get("ask"))
    risk = abs(float(setup.get("entry", 0)) - float(setup.get("stop", 0)))
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return {"status": "SPREAD_UNKNOWN", "source": "NO_BROKER_BID_ASK",
                "risk_price_units": round(risk, 3),
                "spread": None, "execution_quality_verified": False}
    spread = ask-bid
    return {
        "status": "HIGH_COST" if risk > 0 and spread >= risk*0.25 else "MEASURED",
        "source": "EXPLICIT_BID_ASK_REFERENCE", "spread": round(spread, 4),
        "spread_to_stop": round(spread/risk, 3) if risk > 0 else None,
        "execution_quality_verified": True,
    }


def entry_validity(setup, reference, now):
    """Feature 17: entry quote is valid briefly, NOT for the 20m paper lifecycle."""
    stamp = number(reference.get("time"))
    price = number(setup.get("entry"))
    current = number(reference.get("price"))
    atr = number(setup.get("risk")) or (abs(price-float(setup["stop"])) if price is not None else None)
    if stamp is None or price is None:
        return {"status": "UNKNOWN", "entry_valid": False}
    age = now.timestamp()-stamp
    deviation = abs(current-price) if current is not None else None
    tolerance = min(1.0, max(0.3, 0.25*atr)) if atr and atr > 0 else 0.3
    valid = -5 <= age <= 90 and deviation is not None and deviation <= tolerance
    return {
        "status": "VALID" if valid else "EXPIRED_OR_CHANGED",
        "entry_valid": valid, "age_seconds": round(age, 1),
        "expires_at": stamp+90, "price_tolerance": round(tolerance, 3),
        "observed_difference": round(deviation, 3) if deviation is not None else None,
    }


def exposure_check(setup, quick_trades, official_trade=None):
    """Feature 19: annotate cross-stream exposure without forbidding allowed coexistence."""
    side = setup.get("side")
    active = [t for t in (quick_trades or [])
              if isinstance(t, dict) and t.get("status") in ("active", "uncertain_delivery")]
    official = official_trade if isinstance(official_trade, dict) and official_trade.get("status") == "active" else None
    same = sum(t.get("side") == side for t in active)
    opposite = sum(t.get("side") != side for t in active)
    if official:
        same += int(official.get("side") == side)
        opposite += int(official.get("side") != side)
    return {
        "active_quick": len(active), "active_official": bool(official),
        "same_direction": same, "opposite_direction": opposite,
        "warning": "CORRELATED_EXPOSURE" if same else "DIRECTION_CONFLICT" if opposite else "NONE",
        "note": "Cross-stream warning; existing quick-guard stays authoritative",
    }


def adaptive_entry_review(decision, setup, reference, now, previous_policy,
                          quick_trades=None, official_trade=None):
    """Feature 17–20: annotate context; only downgrade unsafe ENTER_NOW."""
    policy = dict(previous_policy)
    policy["warnings"] = list(policy.get("warnings") or [])
    policy["reasons"] = list(policy.get("reasons") or [])
    adapt = ((decision.get("v4") or {}).get("adaptive") or {})
    validity = entry_validity(setup, reference, now)
    cost = execution_cost(setup, reference)
    exposure = exposure_check(setup, quick_trades, official_trade)
    plan = risk_targets(decision, setup)
    action = policy.get("action", "WATCH")
    if action not in ("WATCH", "CAUTIOUS", "ENTER_NOW"):
        action = "WATCH"
    if not validity["entry_valid"]:
        action = "WATCH"
        policy["reasons"].append("مرجع الدخول انتهت صلاحيته أو تغيّر")
    if action == "ENTER_NOW" and cost["status"] == "HIGH_COST":
        action = "CAUTIOUS"
        policy["warnings"].append("تكلفة التنفيذ كبيرة مقارنة بالوقف")
    if action == "ENTER_NOW" and exposure["warning"] != "NONE":
        action = "CAUTIOUS"
        policy["warnings"].append("تعرض متزامن أو اتجاهات متضاربة")
    if action == "ENTER_NOW" and adapt.get("feature_15_correction", {}).get("state") == "REVERSAL_WATCH":
        action = "CAUTIOUS"
        policy["warnings"].append("انعكاس محتمل على M15/H1 يحتاج تأكيد")
    if action == "ENTER_NOW" and adapt.get("feature_11_regime", {}).get("state") == "VOLATILE_SPIKE":
        action = "CAUTIOUS"
        policy["warnings"].append("طفرة تذبذب مفاجئة")
    policy["action"] = action
    policy["policy"] = "adaptive-11-20+"+str(previous_policy.get("policy", "base"))
    return {
        "version": "v4-adaptive-11-20-v1",
        "feature_17_validity": validity,
        "feature_18_risk_targets": plan,
        "feature_19_exposure": exposure,
        "feature_20_execution_cost": cost,
        "entry_policy": policy,
    }


def signal_change_review(previous, decision, now):
    """One-time direction reversal warning for a recent recommendation.

    Does not close/change paper trades; entry validity expires independently.
    """
    if not isinstance(previous, dict) or previous.get("entry_action") not in ("ENTER_NOW", "CAUTIOUS"):
        return None
    created = number(previous.get("signal_observed_at") or previous.get("created"))
    if created is None or not 0 <= now.timestamp()-created <= 1200:
        return None
    side = previous.get("side")
    other = "SELL" if side == "BUY" else "BUY" if side == "SELL" else None
    if not other:
        return None
    checks = (decision.get("checks") or {}).get(other) or []
    score = sum(bool(x) for x in checks)
    if decision.get("side") != other or score < 5:
        return None
    return {
        "old_id": previous.get("id"),
        "old_side": side, "new_side": other,
        "new_score": score, "status": "DIRECTION_REVERSED_REVIEW_ENTRY",
        "disclaimer": "Paper trade remains governed by its independent SL/TP",
    }


def signal_change_message(reversal):
    side = "شراء" if reversal["old_side"] == "BUY" else "بيع"
    opposite = "شراء" if reversal["new_side"] == "BUY" else "بيع"
    return (
        "⚠️ <b>تحديث صلاحية إشارة V4 السريعة</b>\n"
        f"إشارة {side} السابقة لم تعد مناسبة للدخول الجديد بسبب ظهور ترجيح {opposite} "
        f"({reversal['new_score']}/7).\n"
        "⏳ انتظر تأكيد دخول جديد. هذا تحذير عن صلاحية التوصية وليس إغلاقًا للصفقة الورقية."
    )
