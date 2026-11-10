"""Laith V4 paper-signal opportunity tracker, Telegram audit, and MFE/MAE.

Approved selective improvements from features 21–30. They observe and explain
existing decisions; never increase the entry threshold, auto-trade, or infer
broker fills. The existing five-minute cycle remains the detection cadence.
"""
from datetime import datetime, timezone
import math

UTC = timezone.utc
ACTIONS = {"WATCH", "CAUTIOUS", "ENTER_NOW"}


def _finite(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _latest_side(decision):
    """WATCH a plausible dominant side, not a fabricated trade."""
    side = decision.get("side")
    if side in ("BUY", "SELL"):
        return side
    buy, sell = _finite(decision.get("buy")), _finite(decision.get("sell"))
    if buy is None or sell is None or max(buy, sell) < 4 or buy == sell:
        return None
    return "BUY" if buy > sell else "SELL"


def remember_watch(store, decision, now):
    """Log a 5m WAIT without creating a signal or sending an extra message."""
    side = _latest_side(decision or {})
    if not side:
        return None
    score = _finite((decision or {}).get(side.lower()))
    return record_opportunity(store, side, "WATCH", now, score=score)


def record_opportunity(store, side, action, now, *, score=None, signal_id=None):
    """Feature 21: record transitions for one side only, based on *actual* verdict.

    Feature 22: publish a promotion label on the usual signal card (no extra
    messages and no promise of sub-5-minute latency).
    """
    if side not in ("BUY", "SELL") or action not in ACTIONS:
        return None
    stamp = now.timestamp()
    previous = store.get("v4_opportunity_progress") or {}
    if not isinstance(previous, dict):
        previous = {}
    old = previous.get(side) or {}
    age = stamp - (_finite(old.get("time")) or 0)
    if not 0 <= age <= 1800:
        old = {}
    before = old.get("action")
    transition = None
    if before == "WATCH" and action in ("CAUTIOUS", "ENTER_NOW"):
        transition = "WATCH_TO_" + action
    elif before == "CAUTIOUS" and action == "ENTER_NOW":
        transition = "CAUTIOUS_TO_ENTER_NOW"

    record = {"time": stamp, "action": action, "score": score,
              "signal_id": signal_id, "previous_action": before}
    previous[side] = record
    store.set("v4_opportunity_progress", previous)
    if transition:
        event = {"time": now.isoformat(), "side": side, "transition": transition,
                 "score": score, "signal_id": signal_id,
                 "detection_cadence": "5_MINUTE_CYCLE",
                 "paper_only": True}
        journal = store.get("v4_opportunity_transitions") or []
        if not isinstance(journal, list):
            journal = []
        journal.append(event)
        store.set("v4_opportunity_transitions", journal[-300:])
        return event
    return None


def transition_message(event):
    """A concise annotation added to an *already sent* Quick card."""
    if not event:
        return None
    labels = {
        "WATCH_TO_ENTER_NOW": "مراقبة ← ادخل الآن",
        "WATCH_TO_CAUTIOUS": "مراقبة ← ادخل بحذر",
        "CAUTIOUS_TO_ENTER_NOW": "ادخل بحذر ← ادخل الآن",
    }
    label = labels.get(event.get("transition"))
    if not label:
        return None
    return "🔔 تحديث الفرصة: " + label + " (تأكيد عند فحص 5 دقائق)"


def record_telegram_delivery(store, outcome, lane, now=None):
    """Feature 23: persist confirmation/failure WITHOUT retrying uncertain sends.

    No message text, recipient ID, token, URL or arbitrary error payload saved.
    An unknown outcome must not be marked as sent.
    """
    status = getattr(outcome, "status", None)
    if status not in ("sent", "failed", "retry", "uncertain"):
        status = "uncertain"
    ts = (now or datetime.now(UTC)).isoformat()
    counters = store.get("v4_telegram_delivery_counts") or {}
    if not isinstance(counters, dict):
        counters = {}
    counters[status] = int(counters.get(status, 0)) + 1
    store.set("v4_telegram_delivery_counts", counters)
    event = {"at": ts, "lane": lane if lane in ("group", "private") else "unknown",
             "status": status, "acknowledged": status == "sent",
             "message_id": getattr(outcome, "message_id", None) if status == "sent" else None}
    journal = store.get("v4_telegram_delivery_audit") or []
    if not isinstance(journal, list):
        journal = []
    journal.append(event)
    store.set("v4_telegram_delivery_audit", journal[-100:])
    store.set("v4_telegram_delivery_last", event)
    return status == "sent"


def audit_quick_excursion(original, updated, bars):
    """Feature 26: closed-bar MFE/MAE in price units and R, not executable P&L.

    Only observations newer than the previously processed bar and no later
    than updated.last_end are considered. If a stop/target occurs in the same
    OHLC bar, intrabar high/low ordering is UNKNOWN and clearly labelled.
    """
    if not isinstance(original, dict) or not isinstance(updated, dict):
        return updated
    if original.get("status") != "active":
        return updated
    entry, risk = _finite(original.get("entry")), _finite(original.get("risk"))
    side = original.get("side")
    announced = _finite(original.get("announced"))
    end = _finite(updated.get("last_end"))
    if side not in ("BUY", "SELL") or entry is None or risk is None or risk <= 0:
        return updated
    if announced is None or end is None:
        return updated
    prior_end = _finite(original.get("last_end")) or announced
    eligible = [b for b in bars or []
                if getattr(b, "end", None) is not None
                and prior_end < b.end.timestamp() <= end]
    if not eligible:
        return updated
    previous = original.get("excursion") or {}
    if not isinstance(previous, dict):
        previous = {}
    mfe = max(0.0, _finite(previous.get("mfe_price_units")) or 0.0)
    mae = max(0.0, _finite(previous.get("mae_price_units")) or 0.0)
    direction = 1 if side == "BUY" else -1
    for b in eligible:
        high, low = _finite(b.high), _finite(b.low)
        if high is None or low is None or high < low:
            continue
        favorable = (high-entry) if direction == 1 else (entry-low)
        adverse = (entry-low) if direction == 1 else (high-entry)
        mfe, mae = max(mfe, favorable), max(mae, adverse)
    result = dict(updated)
    result["excursion"] = {
        "status": "CLOSED_BAR_HINDSIGHT",
        "mfe_price_units": round(mfe, 3),
        "mae_price_units": round(mae, 3),
        "mfe_r": round(mfe/risk, 3),
        "mae_r": round(mae/risk, 3),
        "last_observed_end": end,
        "intrabar_order_unknown": True,
        "no_broker_fill_or_spread": True,
    }
    return result
