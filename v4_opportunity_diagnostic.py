"""Read-only V4 opportunity diagnostic; never authorizes an entry."""


def diagnose_wait(decision):
    """Preserve missing checks as unknown, not seven failed conditions."""
    checks = decision.get("checks") or {}
    scores = {}
    missing = {}
    for side in ("BUY", "SELL"):
        raw = checks.get(side)
        if isinstance(raw, (list, tuple)) and len(raw) == 7:
            scores[side] = sum(bool(value) for value in raw)
            missing[side] = False
        else:
            scores[side] = None
            missing[side] = True
    research = decision.get("v4") or {}
    zone = research.get("no_trade_zone") or {}
    entry_gate = (research.get("intelligence") or {}).get("entry_gate") or {}
    return {
        "decision": decision.get("side", "WAIT"),
        "reason": decision.get("reason"),
        "buy_score": scores["BUY"],
        "sell_score": scores["SELL"],
        "buy_checks_missing": missing["BUY"],
        "sell_checks_missing": missing["SELL"],
        "zone_reasons": list(zone.get("reasons") or []),
        "entry_gate_reasons": list(entry_gate.get("reasons") or []),
        "eligible_for_review": (
            decision.get("side") == "WAIT"
            and any(score is not None and score >= 5 for score in scores.values())
        ),
    }
