"""Independent V4 emergency reversal watcher.

This module never changes entries, stops, targets, or trade state. It only watches
already-open V4 paper trades and emits a warning when several observable signs
point against the trade direction.
"""
import json


def _score(decision, side):
    checks = (decision.get("checks") or {}).get(side)
    if isinstance(checks, (list, tuple)) and len(checks) == 7:
        return sum(bool(x) for x in checks)
    try:
        return max(0, min(7, int(decision.get(side.lower(), 0))))
    except (TypeError, ValueError):
        return 0


def _opposite(side):
    return "SELL" if side == "BUY" else "BUY"


def _adverse_correction(side, correction):
    direction = (correction or {}).get("direction")
    return ((side == "BUY" and direction == "DOWN")
            or (side == "SELL" and direction == "UP"))


def reversal_snapshot(decision, trade):
    """Return an emergency warning snapshot or None when no reversal alarm exists."""
    side = trade.get("side")
    if side not in ("BUY", "SELL"):
        return None
    opposite = _opposite(side)
    own_score = _score(decision, side)
    opposite_score = _score(decision, opposite)
    research = decision.get("v4") or {}
    correction = research.get("correction") or {}

    reasons = []
    official_opposite = decision.get("side") == opposite
    if official_opposite:
        reasons.append("القرار الرسمي الحالي أصبح بالاتجاه المعاكس")

    failed_break = research.get("breakout_state") == "FAILED_BREAK"
    if failed_break:
        reasons.append("ظهر كسر فاشل ضد استمرار الصفقة")

    strong_adverse_correction = (
        bool(correction.get("triggered"))
        and correction.get("strength") == "STRONG"
        and _adverse_correction(side, correction)
    )
    if strong_adverse_correction:
        reasons.append("تصحيح قوي مُفعّل عكس اتجاه الصفقة")

    opposite_dominance = opposite_score >= 5 and opposite_score >= own_score + 2
    if opposite_dominance:
        reasons.append(
            f"شروط الاتجاه المعاكس أصبحت أقوى: {opposite_score}/7 مقابل {own_score}/7"
        )

    if not reasons:
        return None

    high = official_opposite or strong_adverse_correction or len(reasons) >= 2
    severity = "مرتفعة" if high else "متوسطة"
    return {
        "trade_id": trade.get("id"),
        "kind": trade.get("kind") or "OFFICIAL",
        "side": side,
        "opposite_side": opposite,
        "own_score": own_score,
        "opposite_score": opposite_score,
        "severity": severity,
        "reasons": reasons,
        "price": decision.get("price"),
        "entry": trade.get("entry"),
        "stop": trade.get("stop"),
        "target": trade.get("target") or trade.get("tp1"),
        "correction_direction": correction.get("direction"),
        "correction_strength": correction.get("strength"),
        "correction_target1": correction.get("target1"),
        "correction_target2": correction.get("target2"),
    }


def _fmt(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def emergency_message(snapshot):
    marker = "🚨" if snapshot.get("severity") == "مرتفعة" else "⚠️"
    side_ar = "شراء" if snapshot.get("side") == "BUY" else "بيع"
    opp_ar = "بيع" if snapshot.get("opposite_side") == "SELL" else "شراء"
    reasons = " — ".join(str(x) for x in (snapshot.get("reasons") or [])[:2]) or "انعكاس محتمل"
    lines = [
        f"{marker} <b>طوارئ V4 — احتمال انعكاس</b>",
        f"🔴① وقف/إبطال الصفقة: <b>{_fmt(snapshot.get('stop'))}</b>",
        f"🔴② درجة التحذير: <b>{snapshot.get('severity', '—')}</b>",
        f"🟠③ السعر / الدخول: {_fmt(snapshot.get('price'))} / {_fmt(snapshot.get('entry'))}",
        f"🔵④ الشروط: {side_ar} {snapshot.get('own_score', 0)}/7 | {opp_ar} {snapshot.get('opposite_score', 0)}/7",
        f"🟡⑤ السبب: {reasons}",
    ]
    if snapshot.get("correction_target1") is not None or snapshot.get("correction_target2") is not None:
        lines.append(
            f"🟠⑥ التصحيح المتوقع: {_fmt(snapshot.get('correction_target1'))} → {_fmt(snapshot.get('correction_target2'))}"
        )
    lines.append("⚠️ تحذير فقط؛ لا يغلق الصفقة ولا يغيّر الستوب تلقائيًا.")
    return "\n".join(lines)

def _fingerprint(snapshot):
    return json.dumps({
        "severity": snapshot.get("severity"),
        "reasons": snapshot.get("reasons") or [],
        "own": snapshot.get("own_score"),
        "opp": snapshot.get("opposite_score"),
    }, ensure_ascii=False, sort_keys=True)


def scan_emergencies(store, notifier, decision, official_trade, quick_trades, now):
    """Scan active paper trades and send only new/changed reversal warnings."""
    previous = store.get("v4_emergency_state", {}) or {}
    if not isinstance(previous, dict):
        previous = {}
    next_state = {}
    alerts = []

    candidates = []
    if official_trade and official_trade.get("status", "active") == "active":
        candidates.append(official_trade)
    for trade in quick_trades or []:
        if trade.get("status") != "active":
            continue
        try:
            age = now.timestamp() - float(trade.get("announced", trade.get("created", 0)) or 0)
        except (TypeError, ValueError):
            age = 9999
        # Do not warn on the same observation that just created a quick setup.
        if age < 240:
            continue
        candidates.append(trade)

    for trade in candidates:
        trade_id = str(trade.get("id") or "unknown")
        snapshot = reversal_snapshot(decision, trade)
        if not snapshot:
            continue
        fingerprint = _fingerprint(snapshot)
        next_state[trade_id] = fingerprint
        if previous.get(trade_id) == fingerprint:
            continue
        alerts.append(snapshot)
        if notifier:
            notifier.send(emergency_message(snapshot))

    store.set("v4_emergency_state", next_state)
    return alerts
