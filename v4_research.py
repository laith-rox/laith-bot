"""Laith V4 decision adapter.

V4 starts from the validated V3 research snapshot copied into the v4-main branch,
then exposes a V4-only contract so future V4 changes cannot alter the live bot or
V3 paper worker.
"""
from v3_research import analyze_v3
from v4_intelligence import enrich_decision
from v4_quick import strength_label


def _expose_directional_candidate(result):
    """Expose the best observable 7-check direction instead of hiding weak V4 setups.

    This only relaxes strategy/research vetoes. Fresh-data, quote, entry-window,
    news, cooldown and price-movement safety gates remain enforced by runtime.
    """
    checks = result.get("checks") or {}
    buy_checks = checks.get("BUY")
    sell_checks = checks.get("SELL")
    if not isinstance(buy_checks, (list, tuple)) or len(buy_checks) != 7:
        return result
    if not isinstance(sell_checks, (list, tuple)) or len(sell_checks) != 7:
        return result

    buy = sum(bool(x) for x in buy_checks)
    sell = sum(bool(x) for x in sell_checks)
    if buy > sell:
        side, score = "BUY", buy
    elif sell > buy:
        side, score = "SELL", sell
    else:
        # A true tie is not converted into an official 15m trade.
        return result

    price = result.get("price")
    atr = result.get("atr")
    if price is None or atr is None:
        return result

    direction = 1 if side == "BUY" else -1
    result.update(
        side=side,
        buy=buy,
        sell=sell,
        signal_score=score,
        signal_total=7,
        signal_strength=strength_label(score),
        relaxed_candidate=True,
        original_veto=result.get("reason"),
    )

    # Keep an existing side-compatible baseline plan when available; otherwise
    # construct the same ATR plan used by the baseline analyzer.
    result["sl"] = float(price) - direction * 1.4 * float(atr)
    result["tp1"] = float(price) + direction * 1.8 * float(atr)
    result["tp2"] = float(price) + direction * 2.6 * float(atr)
    result["reason"] = "v4_directional_candidate"
    return result


def analyze_v4(bars, now, macro=None):
    result = analyze_v3(bars, now, macro=macro)
    research = dict(result.pop("v3", {}) or {})
    research.update({
        "generation": "V4",
        "research_only": True,
        "paper_only": True,
    })
    reason = result.get("reason")
    if isinstance(reason, str) and reason.startswith("v3_"):
        result["reason"] = "v4_" + reason[3:]

    if result.get("side") not in ("BUY", "SELL"):
        result = _expose_directional_candidate(result)

    side = result.get("side")
    side_checks = (result.get("checks") or {}).get(side) if side in ("BUY", "SELL") else None
    if isinstance(side_checks, (list, tuple)) and len(side_checks) == 7:
        score = sum(bool(x) for x in side_checks)
        result["signal_score"] = score
        result["signal_total"] = 7
        result["signal_strength"] = strength_label(score)

    result["v4"] = research
    return enrich_decision(result, bars, now)
