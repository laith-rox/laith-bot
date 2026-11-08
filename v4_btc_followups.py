"""Strict post-alert BTC observation journal. Read-only, never broker orders.

Only complete 5m bars strictly AFTER the alert bar are evaluated.
Unobserved gaps and same-bar TP/SL ordering are not scored as wins/losses.
"""
from datetime import datetime, timezone
from math import ceil

UTC = timezone.utc
ACTIVE_KEY = "v4_btc_observed_active"
JOURNAL_KEY = "v4_btc_observed_journal"
MAX_RECORDS = 250


def _journal(store, event):
    history = store.get(JOURNAL_KEY) or []
    history.append(event)
    store.set(JOURNAL_KEY, history[-MAX_RECORDS:])


def start_observation(store, signal, now):
    """Capture only the model signal; it does not mean a manual trade was filled."""
    existing = store.get(ACTIVE_KEY)
    if existing and existing.get("status") == "OPEN":
        return False
    observed = {
        "id": f"btc-{int(now.timestamp())}",
        "created": float(now.timestamp()), "side": signal["side"],
        "entry": float(signal["entry"]), "sl": float(signal["sl"]),
        "original_sl": float(signal["sl"]),
        "tp1": float(signal["tp1"]), "tp2": float(signal["tp2"]),
        "status": "OPEN", "tp1_seen": False, "tp1_alerted": False,
        "last_bar_end": 0, "event": None,
    }
    store.set(ACTIVE_KEY, observed)
    _journal(store, {"kind": "SIGNAL", **observed})
    return True


def _hits(bar, trade):
    side = trade["side"]
    stop = bar.low <= trade["sl"] if side == "BUY" else bar.high >= trade["sl"]
    first = bar.high >= trade["tp1"] if side == "BUY" else bar.low <= trade["tp1"]
    second = bar.high >= trade["tp2"] if side == "BUY" else bar.low <= trade["tp2"]
    return stop, first, second


def _close(store, trade, reason, now, r_multiple=None):
    trade["status"] = "CLOSED"
    trade["event"] = reason
    trade["closed"] = now.timestamp()
    trade["r_multiple"] = r_multiple
    store.set(ACTIVE_KEY, trade)
    _journal(store, {"kind": "CLOSE", **trade})


def btc_status_message(store):
    signal = store.get("v4_btc_status") or {}
    trade = store.get(ACTIVE_KEY) or {}
    return (
        "₿ <b>حالة إشارات البيتكوين</b>\n"
        f"آخر تحليل: {signal.get('status', 'غير متاح')}\n"
        f"سبب الانتظار: {signal.get('reason', 'لا يوجد')}\n"
        f"قوة الشروط: {signal.get('score', 'غير متاح')}/7\n"
        f"إشارة قيد المراقبة: {trade.get('side', 'لا يوجد') if trade.get('status') == 'OPEN' else 'لا يوجد'}\n"
        "المتابعة افتراضية ولا تؤكد تنفيذ صفقة فعلية."
    )


def btc_stats_message(store):
    events = store.get(JOURNAL_KEY) or []
    signals = [e for e in events if e.get("kind") == "SIGNAL"]
    closes = [e for e in events if e.get("kind") == "CLOSE"]
    scored = [e for e in closes if isinstance(e.get("r_multiple"), (float, int))]
    wins = [e for e in scored if e["r_multiple"] > 0]
    total_r = sum(e["r_multiple"] for e in scored)
    ambiguous = len(closes) - len(scored)
    rate = f"{len(wins) / len(scored) * 100:.1f}%" if scored else "غير متاح"
    return (
        "₿ <b>سجل مراقبة البيتكوين</b>\n"
        f"إشارات أُرسلت: {len(signals)}\n"
        f"متابعات أُغلقت: {len(closes)}\n"
        f"نتائج قابلة للقياس: {len(scored)}\n"
        f"غير محسومة/غير مكتملة: {ambiguous}\n"
        f"نسبة النتائج الموجبة في النموذج: {rate}\n"
        f"مجموع R النموذجي قبل الرسوم: {total_r:+.2f}\n"
        "هذه ليست أرباح حساب حقيقي، ولا تفترض تنفيذ الإشارات."
    )


def follow_observation(store, notifier, provider, now):
    trade = store.get(ACTIVE_KEY) or {}
    if trade.get("status") != "OPEN":
        return "idle"
    try:
        m5 = provider.candles(now, 5)
    except Exception as exc:
        store.set("v4_btc_follow_error", type(exc).__name__)
        return "data_wait"
    if not m5:
        return "data_wait"
    # A complete candle that started before Telegram delivery is never counted.
    first_allowed_start = int(ceil(trade["created"] / 300) * 300)
    prior_end = int(trade.get("last_bar_end") or first_allowed_start)
    candidates = [b for b in m5 if b.start.timestamp() >= prior_end]
    if not candidates:
        return "no_new_closed_bar"
    for bar in candidates:
        bar_start = int(bar.start.timestamp())
        if bar_start != prior_end:
            _close(store, trade, "DATA_GAP_UNVERIFIED", now)
            return "gap"
        prior_end = int(bar.end.timestamp())
        trade["last_bar_end"] = prior_end
        stopped, tp1, tp2 = _hits(bar, trade)
        if stopped and (tp1 or tp2):
            _close(store, trade, "SAME_BAR_AMBIGUOUS", now)
            return "ambiguous"
        if stopped:
            risk = abs(trade["entry"] - trade["original_sl"])
            stopped_at_be = trade["tp1_seen"] and trade["sl"] == trade["entry"]
            result = 0.0 if stopped_at_be else -abs(trade["entry"] - trade["sl"]) / risk
            _close(store, trade, "MODEL_STOP", now, result)
            if notifier:
                notifier.send(
                    f"₿ نموذج متابعة BTC/USD: وصل مستوى الوقف المرجعي — {trade['sl']:,.2f}$.\n"
                    "النتيجة تحليلية فقط، لا تؤكد تنفيذ صفقة أو خسارة فعلية."
                )
            return "stop"
        if tp2:
            risk = abs(trade["entry"] - trade["original_sl"])
            gain = abs(trade["tp2"] - trade["entry"]) / risk
            _close(store, trade, "MODEL_TP2", now, gain)
            if notifier:
                notifier.send(
                    f"₿ نموذج متابعة BTC/USD: وصل المستوى الثاني — {trade['tp2']:,.2f}$.\n"
                    "متابعة سعرية فقط، ولا تثبت ربح حساب تداول."
                )
            return "tp2"
        if tp1 and not trade["tp1_seen"]:
            trade["tp1_seen"] = True
            # The paper BE reference is only effective starting NEXT candle.
            trade["sl"] = trade["entry"]
            store.set(ACTIVE_KEY, trade)
        if trade["tp1_seen"] and not trade["tp1_alerted"] and notifier:
            if notifier.send(
                f"₿ BTC/USD وصل الهدف الأول {trade['tp1']:,.2f}$ ✅\n"
                f"🛡️ اقتراح حماية: نقل الوقف إلى الدخول {trade['entry']:,.2f}$ بعد التحقق من السعر والسبريد.\n"
                "لا يتم تحريك أي أمر حقيقي تلقائيًا."
            ) is True:
                trade["tp1_alerted"] = True
                store.set(ACTIVE_KEY, trade)
    store.set(ACTIVE_KEY, trade)
    if now.timestamp() - trade["created"] >= 12 * 3600:
        _close(store, trade, "MODEL_EXPIRED_UNSCORED", now)
        return "expired"
    return "observing"
