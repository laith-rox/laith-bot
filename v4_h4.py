"""Independent four-hour paper-trade stream for Laith V4.

This module is intentionally isolated from the official V4 strategy and the
five-minute quick stream. It evaluates each newly closed four-hour candle,
keeps at most one H4 paper trade active, and records its own outcomes.
"""
from datetime import datetime, timezone
import hashlib
import json
import math

from engine import advance_trade, atr, ema, macd, rsi
from market import Bar

UTC = timezone.utc
H4_MINUTES = 240
H4_SECONDS = H4_MINUTES * 60
H4_MIN_5M_BARS = 36


def resample_h4(bars, now):
    """Aggregate closed 5m bars into closed 4h UTC candles.

    A four-hour bucket may include a normal market-maintenance gap, but partial
    current candles and thin/incomplete buckets are rejected.
    """
    groups = {}
    for bar in bars or []:
        if getattr(bar, "minutes", None) != 5:
            continue
        bucket = int(bar.start.timestamp()) // H4_SECONDS * H4_SECONDS
        groups.setdefault(bucket, []).append(bar)

    result = []
    settle = now.timestamp() - 10
    for bucket, group in sorted(groups.items()):
        bucket_end = bucket + H4_SECONDS
        if bucket_end > settle:
            continue
        group = sorted(group, key=lambda item: item.start)
        unique = {int(item.start.timestamp()): item for item in group}
        group = [unique[key] for key in sorted(unique)]
        if len(group) < H4_MIN_5M_BARS:
            continue
        if (group[-1].end - group[0].start).total_seconds() < 3 * 60 * 60:
            continue
        result.append(Bar(
            datetime.fromtimestamp(bucket, UTC),
            group[0].open,
            max(item.high for item in group),
            min(item.low for item in group),
            group[-1].close,
            H4_MINUTES,
        ))
    return result


def _structure_state(bars):
    if len(bars) < 8:
        return "NEUTRAL"
    previous = bars[-8:-4]
    recent = bars[-4:]
    higher_high = max(item.high for item in recent) > max(item.high for item in previous)
    higher_low = min(item.low for item in recent) > min(item.low for item in previous)
    lower_high = max(item.high for item in recent) < max(item.high for item in previous)
    lower_low = min(item.low for item in recent) < min(item.low for item in previous)
    if higher_high and higher_low:
        return "BULLISH"
    if lower_high and lower_low:
        return "BEARISH"
    return "MIXED"


def _pivot_levels(bars, price):
    supports, resistances = [], []
    window = bars[-24:] if len(bars) > 24 else bars
    for index in range(1, len(window) - 1):
        left, current, right = window[index - 1:index + 2]
        if current.low <= left.low and current.low <= right.low and current.low < price:
            supports.append(float(current.low))
        if current.high >= left.high and current.high >= right.high and current.high > price:
            resistances.append(float(current.high))
    support = max(supports) if supports else None
    resistance = min(resistances) if resistances else None
    return support, resistance


def _correction_map(side, price, e20, e50, support, resistance, atr_value, last_bar, rsi_value):
    if side == "BUY":
        candidates = [value for value in (e20, support, e50) if value is not None and value < price]
        candidates = sorted(set(float(value) for value in candidates), reverse=True)
        counter = int(last_bar.close < last_bar.open) + int(rsi_value >= 65) + int(abs(price - e20) >= atr_value)
        return {
            "direction": "DOWN",
            "strength": "STRONG" if counter >= 2 else "MEDIUM" if counter == 1 else "WEAK",
            "target1": candidates[0] if candidates else None,
            "target2": candidates[1] if len(candidates) > 1 else None,
        }
    if side == "SELL":
        candidates = [value for value in (e20, resistance, e50) if value is not None and value > price]
        candidates = sorted(set(float(value) for value in candidates))
        counter = int(last_bar.close > last_bar.open) + int(rsi_value <= 35) + int(abs(price - e20) >= atr_value)
        return {
            "direction": "UP",
            "strength": "STRONG" if counter >= 2 else "MEDIUM" if counter == 1 else "WEAK",
            "target1": candidates[0] if candidates else None,
            "target2": candidates[1] if len(candidates) > 1 else None,
        }
    return {"direction": None, "strength": "UNAVAILABLE", "target1": None, "target2": None}


def analyze_h4(h4_bars):
    """Analyze only H4 candles and return an independent paper decision."""
    if len(h4_bars) < 45:
        return {"side": "WAIT", "reason": "h4_insufficient_history", "buy": 0, "sell": 0}

    closes = [float(item.close) for item in h4_bars]
    e20_series = ema(closes, 20)
    e50_series = ema(closes, 50)
    e20 = e20_series[-1]
    e50 = e50_series[-1]
    e20_prev = e20_series[-4]
    macd_value = macd(closes)
    rsi_value = rsi(closes)
    atr_value = atr(h4_bars)
    last = h4_bars[-1]
    price = float(last.close)
    structure = _structure_state(h4_bars)
    support, resistance = _pivot_levels(h4_bars, price)

    buy_checks = [
        e20 > e50,
        e20 > e20_prev,
        macd_value > 0,
        50 <= rsi_value <= 70,
        price > e20,
        last.close > last.open,
        structure == "BULLISH",
    ]
    sell_checks = [
        e20 < e50,
        e20 < e20_prev,
        macd_value < 0,
        30 <= rsi_value <= 50,
        price < e20,
        last.close < last.open,
        structure == "BEARISH",
    ]
    buy_score, sell_score = sum(buy_checks), sum(sell_checks)
    not_extended = abs(price - e20) <= 1.7 * atr_value

    side = "WAIT"
    reason = "h4_conditions_not_aligned"
    if not_extended and buy_score >= 5 and buy_score >= sell_score + 2:
        side, reason = "BUY", "h4_buy_conditions_met"
    elif not_extended and sell_score >= 5 and sell_score >= buy_score + 2:
        side, reason = "SELL", "h4_sell_conditions_met"
    elif not not_extended:
        reason = "h4_price_extended"

    base_risk = 1.35 * atr_value
    risk_distance = base_risk
    if side == "BUY" and support is not None:
        structural = price - support + 0.15 * atr_value
        if 0.7 * atr_value <= structural <= 2.2 * atr_value:
            risk_distance = max(1.05 * atr_value, structural)
    elif side == "SELL" and resistance is not None:
        structural = resistance - price + 0.15 * atr_value
        if 0.7 * atr_value <= structural <= 2.2 * atr_value:
            risk_distance = max(1.05 * atr_value, structural)

    if side == "BUY" and resistance is not None and resistance - price < 0.75 * risk_distance:
        side, reason = "WAIT", "h4_resistance_too_close"
    elif side == "SELL" and support is not None and price - support < 0.75 * risk_distance:
        side, reason = "WAIT", "h4_support_too_close"

    correction_side = side
    if correction_side == "WAIT":
        correction_side = "BUY" if buy_score > sell_score else "SELL" if sell_score > buy_score else None
    correction = _correction_map(
        correction_side, price, e20, e50, support, resistance, atr_value, last, rsi_value
    )

    direction = 1 if side == "BUY" else -1
    sl = price - direction * risk_distance if side != "WAIT" else None
    tp1 = price + direction * 1.4 * risk_distance if side != "WAIT" else None
    tp2 = price + direction * 2.2 * risk_distance if side != "WAIT" else None
    return {
        "side": side,
        "reason": reason,
        "bar": last.end.isoformat(),
        "price": price,
        "atr": atr_value,
        "rsi": rsi_value,
        "macd": macd_value,
        "ema20": e20,
        "ema50": e50,
        "buy": buy_score,
        "sell": sell_score,
        "checks": {"BUY": buy_checks, "SELL": sell_checks},
        "structure": structure,
        "support": support,
        "resistance": resistance,
        "not_extended": not_extended,
        "risk_distance": risk_distance,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "correction": correction,
    }


def _strength(score):
    if score >= 6:
        return "قوية"
    if score == 5:
        return "متوسطة"
    return "ضعيفة"


def _strength_marker(score):
    return "🟢" if score >= 6 else "🟡" if score == 5 else "🔴"


def _fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _side_ar(side):
    return "شراء" if side == "BUY" else "بيع" if side == "SELL" else "انتظار"


def _correction_dir_ar(direction):
    return {"DOWN": "نزول", "UP": "صعود"}.get(direction, "غير متاح")


def make_h4_trade(decision, now, reference_price):
    side = decision["side"]
    if side not in ("BUY", "SELL"):
        raise ValueError("cannot_open_h4_wait")
    direction = 1 if side == "BUY" else -1
    risk_distance = float(decision["risk_distance"])
    entry = float(reference_price)
    key = f"V4H4:{decision['bar']}:{side}"
    return {
        "id": hashlib.sha256(key.encode()).hexdigest()[:12],
        "generation": "V4",
        "kind": "H4",
        "paper_only": True,
        "side": side,
        "entry": entry,
        "initial_sl": entry - direction * risk_distance,
        "stop": entry - direction * risk_distance,
        "tp1": entry + direction * 1.4 * risk_distance,
        "tp2": entry + direction * 2.2 * risk_distance,
        "tp1_hit": False,
        "created": now.timestamp(),
        "announced": now.timestamp(),
        "last_end": None,
        "bar": decision["bar"],
        "status": "active",
        "outcome": None,
        "exit": None,
        "closed": None,
        "r": None,
        "score": decision[side.lower()],
        "buy_score": decision["buy"],
        "sell_score": decision["sell"],
        "strength": _strength(decision[side.lower()]),
        "atr_h4": decision["atr"],
        "rsi_h4": decision["rsi"],
        "structure_h4": decision["structure"],
        "support_h4": decision["support"],
        "resistance_h4": decision["resistance"],
        "correction_h4": decision["correction"],
        "data_gap": False,
        "delivery_uncertain": False,
    }


def h4_open_message(trade):
    score = int(trade.get("score", 0) or 0)
    correction = trade.get("correction_h4") or {}
    lines = [
        "🟦 <b>صفقة الـ4 ساعات</b>",
        "",
        f"الاتجاه: <b>{_side_ar(trade.get('side'))}</b>",
        f"{_strength_marker(score)} القوة: <b>{trade.get('strength', '—')}</b> | الشروط: {score}/7",
        f"📊 شراء {trade.get('buy_score', 0)}/7 | بيع {trade.get('sell_score', 0)}/7",
        f"💰 الدخول المرجعي: <b>{_fmt(trade.get('entry'))}</b>",
        f"🛑 وقف الخسارة: {_fmt(trade.get('stop'))}",
        f"🎯 الهدف 1: {_fmt(trade.get('tp1'))}",
        f"🎯 الهدف 2: {_fmt(trade.get('tp2'))}",
        f"📐 هيكل H4: {trade.get('structure_h4', '—')} | RSI: {_fmt(trade.get('rsi_h4'))}",
        f"دعم: {_fmt(trade.get('support_h4'))} | مقاومة: {_fmt(trade.get('resistance_h4'))}",
    ]
    if correction.get("direction"):
        lines.extend([
            f"↩️ التصحيح المتوقع: {_correction_dir_ar(correction.get('direction'))} | القوة: {correction.get('strength', '—')}",
            f"🎯 أهداف التصحيح: {_fmt(correction.get('target1'))} ثم {_fmt(correction.get('target2'))}",
        ])
    lines.extend(["", "📄 صفقة ورقية مستقلة عن السريع وعن V4 الرسمي."])
    return "\n".join(lines)


def h4_wait_message(decision):
    reason_map = {
        "h4_conditions_not_aligned": "الشروط غير متوافقة للدخول",
        "h4_price_extended": "السعر متمدد عن متوسط H4",
        "h4_resistance_too_close": "المقاومة قريبة من شراء محتمل",
        "h4_support_too_close": "الدعم قريب من بيع محتمل",
        "h4_insufficient_history": "تاريخ H4 غير كافٍ",
    }
    return (
        "🟦 <b>صفقة الـ4 ساعات — لا دخول</b>\n\n"
        f"📊 شروط الشراء: {decision.get('buy', 0)}/7 | شروط البيع: {decision.get('sell', 0)}/7\n"
        f"السبب: {reason_map.get(decision.get('reason'), decision.get('reason', '—'))}\n"
        f"دعم: {_fmt(decision.get('support'))} | مقاومة: {_fmt(decision.get('resistance'))}\n\n"
        "سيعاد التقييم عند إغلاق شمعة 4 ساعات التالية."
    )


def h4_follow_message(trade, decision):
    score = decision.get(trade.get("side", "").lower(), 0)
    return (
        "🟦 <b>صفقة الـ4 ساعات — متابعة</b>\n\n"
        f"الصفقة الحالية: <b>{_side_ar(trade.get('side'))}</b> من {_fmt(trade.get('entry'))}\n"
        f"الشروط الحالية لنفس الاتجاه: {score}/7\n"
        f"🛑 الوقف الحالي: {_fmt(trade.get('stop'))}\n"
        f"🎯 الهدف 1: {_fmt(trade.get('tp1'))} | الهدف 2: {_fmt(trade.get('tp2'))}\n\n"
        "لن تُفتح صفقة H4 ثانية فوق الصفقة الحالية."
    )


def h4_close_message(trade, stats):
    outcome_ar = {
        "TP2": "الهدف 2",
        "STOP": "وقف الخسارة",
        "PROTECTED_STOP": "وقف محمي",
        "AMBIGUOUS": "نتيجة غير محسومة",
    }.get(trade.get("outcome"), trade.get("outcome") or "إغلاق")
    return (
        "🟦 <b>إغلاق صفقة الـ4 ساعات</b>\n\n"
        f"النتيجة: <b>{outcome_ar}</b>\n"
        f"الدخول: {_fmt(trade.get('entry'))} | الخروج: {_fmt(trade.get('exit'))}\n"
        f"R: {_fmt(trade.get('r'))}\n"
        f"📊 سجل H4 المقاس: {stats.get('positive', 0)} موجب / {stats.get('negative', 0)} سالب من {stats.get('measured', 0)}"
    )


def _ensure_table(store):
    store.db.execute("CREATE TABLE IF NOT EXISTS v4_h4_paper(id TEXT PRIMARY KEY, data TEXT NOT NULL)")
    store.db.commit()


def _h4_rows(store):
    _ensure_table(store)
    rows = store.db.execute("SELECT data FROM v4_h4_paper ORDER BY rowid").fetchall()
    return [json.loads(row[0]) for row in rows]


def _h4_stats(store):
    measured = []
    for trade in _h4_rows(store):
        try:
            value = float(trade.get("r"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            measured.append(value)
    stats = {
        "measured": len(measured),
        "positive": sum(value > 0 for value in measured),
        "negative": sum(value < 0 for value in measured),
        "flat": sum(value == 0 for value in measured),
        "net_r": sum(measured),
    }
    store.set("v4_h4_stats", stats)
    return stats


def process_h4(store, notifier, bars, now):
    """Advance the H4 paper trade and evaluate exactly once per new closed H4 candle."""
    _ensure_table(store)
    events = []
    active = store.get("v4_h4_active")
    if active:
        updated, trade_events = advance_trade(active, bars)
        if updated != active:
            if updated.get("status") == "closed":
                with store.db:
                    store.db.execute(
                        "INSERT OR REPLACE INTO v4_h4_paper(id,data) VALUES (?,?)",
                        (updated["id"], json.dumps(updated, allow_nan=False)),
                    )
                store.set("v4_h4_active", None)
                stats = _h4_stats(store)
                if notifier:
                    notifier.send(h4_close_message(updated, stats))
                events.append({"kind": "closed", "trade": updated})
                active = None
            else:
                store.set("v4_h4_active", updated)
                active = updated

    h4_bars = resample_h4(bars, now)
    if not h4_bars:
        return events
    latest_bar = h4_bars[-1].end.isoformat()
    if store.get("v4_h4_last_bar") == latest_bar:
        return events

    decision = analyze_h4(h4_bars)
    store.set("v4_h4_last_analysis", decision)
    store.set("v4_h4_last_bar", latest_bar)

    if active:
        if notifier:
            notifier.send(h4_follow_message(active, decision))
        events.append({"kind": "follow", "decision": decision})
        return events

    if decision.get("side") not in ("BUY", "SELL"):
        store.set("v4_h4_last_block", decision.get("reason"))
        if notifier:
            notifier.send(h4_wait_message(decision))
        events.append({"kind": "wait", "decision": decision})
        return events

    reference_price = float(bars[-1].close)
    if abs(reference_price - float(decision["price"])) > 0.35 * float(decision["atr"]):
        blocked = dict(decision, side="WAIT", reason="h4_reference_price_moved")
        store.set("v4_h4_last_block", "h4_reference_price_moved")
        if notifier:
            notifier.send(h4_wait_message(blocked))
        events.append({"kind": "wait", "decision": blocked})
        return events

    trade = make_h4_trade(decision, now, reference_price)
    store.set("v4_h4_active", trade)
    store.set("v4_h4_last_block", None)
    if notifier:
        notifier.send(h4_open_message(trade))
    events.append({"kind": "open", "trade": trade, "decision": decision})
    return events
