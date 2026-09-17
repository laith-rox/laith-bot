"""Detailed V4-only post-trade diagnosis.

The labels are deterministic research tags. They are used to count recurring
failure contexts and do not imply causation when market data cannot prove it.
"""
from collections import Counter
import math


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _negative_trade(trade):
    r_value = _number(trade.get("r"))
    return trade.get("outcome") in {"STOP", "TIME"} or (r_value is not None and r_value < 0)


def classify_trade_lesson(trade):
    """Classify the strongest observable failure context for a closed losing trade."""
    if not _negative_trade(trade):
        return None

    research = trade.get("research_v4") or {}
    intelligence = research.get("intelligence") or trade.get("intelligence") or {}
    correction = research.get("correction") or {}
    risk = research.get("structural_risk") or {}
    risk_reasons = [str(x) for x in (trade.get("risk_reasons") or [])]
    side = trade.get("side")
    r_value = _number(trade.get("r"))

    # Quick setups explicitly carry these runtime observations.
    if any("خبر" in reason or "اقتصادي" in reason for reason in risk_reasons):
        reason = "news_exposure"
    elif any("تحرك عن سعر التحليل" in reason for reason in risk_reasons):
        reason = "late_entry_price_moved"
    elif any("مخزنة" in reason or "متأخر" in reason for reason in risk_reasons):
        reason = "stale_or_fallback_data"
    elif (intelligence.get("data_quality") or {}).get("label") in {"GAP", "STALE"}:
        reason = "data_quality"
    elif research.get("breakout_state") == "FAILED_BREAK" or trade.get("breakout_state") == "FAILED_BREAK":
        reason = "failed_breakout"
    elif (
        correction.get("triggered")
        and correction.get("strength") == "STRONG"
        and ((side == "BUY" and correction.get("direction") == "DOWN")
             or (side == "SELL" and correction.get("direction") == "UP"))
    ):
        reason = "adverse_correction"
    elif research.get("macro_alignment") in {"CONFLICT", "STRONG_CONFLICT"}:
        reason = "macro_conflict"
    else:
        risk_atr = _number(risk.get("risk_atr"))
        room_r = _number(risk.get("room_r"))
        if risk_atr is not None and risk_atr < 0.75:
            reason = "stop_too_tight_for_structure"
        elif room_r is not None and room_r < 1.40:
            reason = "opposing_structure_or_hidden_level"
        elif research.get("volatility_regime") in {"HIGH", "EXTREME"}:
            reason = "high_volatility"
        else:
            reason = "stop_before_followthrough"

    return {
        "reason": reason,
        "side": side,
        "outcome": trade.get("outcome"),
        "r": r_value,
        "confidence": (intelligence.get("confidence") or {}).get("score"),
        "breakout": research.get("breakout_state") or trade.get("breakout_state"),
        "volatility": research.get("volatility_regime") or trade.get("volatility_regime"),
        "macro": research.get("macro_alignment") or trade.get("macro_alignment"),
        "risk_atr": _number(risk.get("risk_atr")),
        "room_r": _number(risk.get("room_r")),
    }


def record_trade_lesson(store, trade, stream="official"):
    """Append one idempotent lesson and maintain counts by cause and stream."""
    lesson = trade.get("learning") or classify_trade_lesson(trade)
    if not lesson:
        return None
    trade_id = str(trade.get("id") or "")
    key = f"{stream}:{trade_id}"
    journal = store.get("v4_learning_journal", []) or []
    if not isinstance(journal, list):
        journal = []
    if any(isinstance(item, dict) and item.get("key") == key for item in journal):
        return lesson

    item = dict(lesson)
    item.update(key=key, trade_id=trade_id, stream=stream, closed=trade.get("closed"))
    journal.append(item)
    journal = journal[-300:]
    store.set("v4_learning_journal", journal)

    causes = Counter(str(item.get("reason") or "unknown") for item in journal if isinstance(item, dict))
    streams = Counter(str(item.get("stream") or "unknown") for item in journal if isinstance(item, dict))
    store.set("v4_learning_summary", {
        "losses": len(journal),
        "by_reason": dict(causes),
        "by_stream": dict(streams),
        "top_reason": causes.most_common(1)[0][0] if causes else None,
    })
    store.set("v4_last_learning", item)
    return lesson
