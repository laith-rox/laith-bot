"""Two-brain decision support for Laith V4 paper-only Telegram signals.

Market brain analyzes competing scenarios and risk. Execution brain evaluates a
pre-existing entry policy without promoting blocked or weak candidates.  The
ten feature diagnostics are observable heuristics, NOT calibrated probabilities.
No broker actions, configuration changes, or self-modifying strategy rules.
"""
from collections import defaultdict
from datetime import datetime, timezone
import math

UTC = timezone.utc


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _side(decision):
    buy = _number(decision.get("buy")) or 0
    sell = _number(decision.get("sell")) or 0
    if buy > sell:
        return "BUY"
    if sell > buy:
        return "SELL"
    return decision.get("side") if decision.get("side") in ("BUY", "SELL") else "WAIT"


def _strategy(research):
    kind = str(research.get("breakout_state") or "")
    if kind == "RETEST_HELD":
        return "RETEST"
    if kind == "CONFIRMED_BREAK":
        return "BREAKOUT"
    if kind == "FAILED_BREAK":
        return "REVERSAL_WATCH"
    return "TREND"


def market_brain(decision, bars, now):
    """First brain: diagnose both scenarios using existing V4 evidence."""
    research = decision.get("v4") or {}
    intelligence = research.get("intelligence") or {}
    checks = decision.get("checks") or {}
    preferred = _side(decision)
    trend = (decision.get("context") or {}).get("trend")
    buy = sum(bool(v) for v in (checks.get("BUY") or [])[:7])
    sell = sum(bool(v) for v in (checks.get("SELL") or [])[:7])
    plan = intelligence.get("wait_plan") or {}
    quality = intelligence.get("data_quality") or {}
    breakout = str(research.get("breakout_state") or "UNAVAILABLE")
    last = bars[-1] if bars else None
    wick_trap = False
    if last is not None:
        try:
            span = float(last.high) - float(last.low)
            if span > 0:
                upper = float(last.high) - max(float(last.open), float(last.close))
                lower = min(float(last.open), float(last.close)) - float(last.low)
                wick_trap = (preferred == "BUY" and upper > 0.6 * span) or (
                    preferred == "SELL" and lower > 0.6 * span
                )
        except (AttributeError, TypeError, ValueError):
            wick_trap = False

    risk = research.get("structural_risk") or {}
    correction = research.get("correction") or {}
    macro = str(research.get("macro_alignment") or "UNAVAILABLE")
    data_state = quality.get("label", "UNAVAILABLE")
    return {
        "version": "dual-brain-v1",
        "paper_only": True,
        "market_scenarios": {
            "preferred": preferred,
            "buy_support": buy,
            "sell_support": sell,
            "buy_trigger": _number(plan.get("buy_trigger")),
            "sell_trigger": _number(plan.get("sell_trigger")),
            "trend": trend,
            "alternative": "SELL" if preferred == "BUY" else "BUY" if preferred == "SELL" else "WAIT",
        },
        "liquidity": {
            "breakout": breakout,
            "failed_break": breakout == "FAILED_BREAK",
            "wick_trap_warning": bool(wick_trap),
        },
        "timing": {"state": "NEEDS_LIVE_REFERENCE"},
        "flexible_rules": {"five_of_seven_possible": True, "quality_not_probability": True},
        "learning": {"mode": "AUDIT_ONLY"},
        "missed_opportunities": {"mode": "HINDSIGHT_AUDIT"},
        "risk": {
            "structural_stop": _number(risk.get("stop")),
            "room_r": _number(risk.get("room_r")),
            "correction_direction": correction.get("direction"),
            "extreme_volatility": research.get("volatility_regime") == "EXTREME",
            "quick_be_review_after_usd_move": 2.0,
        },
        "external": {"macro_alignment": macro, "news": "CHECK_AT_EXECUTION"},
        "data_quality": {"state": data_state, "recent_gap": bool(quality.get("recent_gap"))},
        "strategy": {"current": _strategy(research), "comparison": "NEEDS_CLOSED_SAMPLES"},
    }


def _strategy_results(closed_trades):
    groups = defaultdict(list)
    for row in (closed_trades or [])[-200:]:
        if not isinstance(row, dict) or row.get("status") != "closed":
            continue
        value = _number(row.get("r"))
        if value is None:
            continue
        key = _strategy(row)
        groups[key].append(value)
    result = {}
    for key, values in sorted(groups.items()):
        result[key] = {
            "sample": len(values),
            "mean_r": round(sum(values) / len(values), 3),
            "positive": sum(value > 0 for value in values),
            "eligible_for_comparison": len(values) >= 5,
        }
    return result


def execution_brain(decision, setup, reference, now, base_policy, *,
                    closed_trades=None, learning_summary=None, news_clear=True):
    """Second brain: add evidence, safely downgrade only, never escalate policy."""
    market = market_brain(decision, None, now)
    result = dict(base_policy)
    result["reasons"] = list(base_policy.get("reasons") or [])
    result["warnings"] = list(base_policy.get("warnings") or [])
    action = base_policy.get("action", "WATCH")
    if action not in ("WATCH", "CAUTIOUS", "ENTER_NOW"):
        action = "WATCH"

    age = None
    stamp = _number(reference.get("time"))
    if stamp is not None:
        age = now.timestamp() - stamp
    price = _number(setup.get("entry"))
    candle_open = _number(reference.get("candle_open"))
    atr = _number(decision.get("atr"))
    moved_atr = None
    if price is not None and candle_open is not None and atr and atr > 0:
        moved_atr = round(abs(price - candle_open) / atr, 3)
    valid_data = (
        age is not None and -5 <= age <= 90
        and bool(reference.get("timing_aligned"))
        and not bool(setup.get("cached_market_data"))
        and not bool(market["data_quality"].get("recent_gap"))
    )
    # Safety cannot be relaxed by the second brain, including stale prices.
    if not valid_data:
        action = "WATCH"
        result["reasons"].append("العقل الثاني: بيانات أو توقيت السعر غير آمن")
    if action == "ENTER_NOW" and market["liquidity"]["failed_break"]:
        action = "CAUTIOUS"
        result["warnings"].append("العقل الأول: احتمال فخ كسر فاشل")
    if action == "ENTER_NOW" and market["risk"]["extreme_volatility"]:
        action = "CAUTIOUS"
        result["warnings"].append("العقل الأول: تذبذب متطرف")
    if action == "ENTER_NOW" and market["liquidity"]["wick_trap_warning"]:
        action = "CAUTIOUS"
        result["warnings"].append("العقل الأول: ذيل شمعة يوحي برفض السعر")
    # A missing news calendar never increases confidence.
    if not news_clear and action == "ENTER_NOW":
        action = "CAUTIOUS"
        result["warnings"].append("تقويم الأخبار غير واضح")
    result["action"] = action
    result["policy"] = "dual-brain-v1+" + str(base_policy.get("policy", "base"))

    entry = _number(setup.get("entry"))
    stop = _number(setup.get("stop"))
    target = _number(setup.get("target"))
    rr = (abs(target-entry) / abs(entry-stop)
          if entry is not None and stop is not None and target is not None
          and abs(entry-stop) > 1e-9 else None)
    comparisons = _strategy_results(closed_trades)
    strategy = market["strategy"]["current"]
    sample = comparisons.get(strategy, {}).get("sample", 0)
    learning = learning_summary if isinstance(learning_summary, dict) else {}
    return {
        "version": "dual-brain-v1",
        "paper_only": True,
        "market": market,
        "execution": {
            "action": action,
            "base_action": base_policy.get("action", "WATCH"),
            "reference_age_seconds": round(age, 2) if age is not None else None,
            "price_move_atr": moved_atr,
            "data_safe": valid_data,
            "news_clear": bool(news_clear),
            "rr": round(rr, 2) if rr is not None else None,
            "break_even_review_after_usd_move": 2.0,
            "warnings": result["warnings"][-4:],
            "reason": result["reasons"][0] if result["reasons"] else "مراجعة شروط الدخول",
        },
        "learning": {
            "audited_losses": int(learning.get("losses") or 0),
            "mode": "REVIEW_ONLY_NO_AUTO_TUNING",
        },
        "missed_opportunities": {"mode": "HINDSIGHT_AUDIT"},
        "strategy_comparison": {
            "current": strategy,
            "current_sample": sample,
            "eligible": sample >= 5,
            "closed_sample_stats": comparisons,
        },
        "entry_policy": result,
    }


def audit_watch_decisions(store, bars, now):
    """Audit prior WATCH decisions 20m later, WITHOUT declaring a simulated fill."""
    if not bars:
        return 0
    history = store.get("v4_entry_decisions", []) or []
    if not isinstance(history, list):
        return 0
    audited = store.get("v4_watch_audit", []) or []
    if not isinstance(audited, list):
        audited = []
    seen = {row.get("key") for row in audited if isinstance(row, dict)}
    added = 0
    for decision in history[-300:]:
        if not isinstance(decision, dict) or decision.get("action") != "WATCH":
            continue
        key = str(decision.get("id") or "")
        if not key or key in seen:
            continue
        try:
            opened = datetime.fromisoformat(decision["time"]).timestamp()
        except (KeyError, TypeError, ValueError):
            continue
        if now.timestamp() - opened < 1200:
            continue
        # Compare to the first closed 5m candle at/after 20m, not current price.
        target_end = opened + 1200
        future = next((bar for bar in bars
                       if target_end <= bar.end.timestamp() <= target_end + 300), None)
        if future is None:
            continue
        side = decision.get("side")
        entry = _number(decision.get("entry"))
        stop = _number(decision.get("stop"))
        if side not in ("BUY", "SELL") or entry is None or stop is None or abs(entry-stop) < 1e-9:
            continue
        direction = 1 if side == "BUY" else -1
        hypothetical_r = round(direction * (float(future.close) - entry) / abs(entry-stop), 2)
        audited.append({
            "key": key, "time": decision["time"], "side": side,
            "action": "WATCH", "hypothetical_20m_r": hypothetical_r,
            "possible_missed_move": hypothetical_r >= 0.5,
            "status": "HINDSIGHT_ONLY_NOT_AN_EXECUTED_TRADE",
        })
        seen.add(key)
        added += 1
    if added:
        store.set("v4_watch_audit", audited[-500:])
        store.set("v4_watch_audit_summary", {
            "audited": len(audited[-500:]),
            "possible_missed_moves": sum(bool(x.get("possible_missed_move")) for x in audited[-500:]),
            "limitations": "Close-only hindsight; no fills, spread, slippage or intrabar path.",
        })
    return added
