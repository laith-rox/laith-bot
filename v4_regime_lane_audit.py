"""Read-only comparison of official and quick V4 direction against market regime.

Never authorizes entries, bypasses runtime gates, or predicts profitability.
"""


def regime_lane_audit(decision, quick=None):
    research = decision.get("v4") or {}
    adaptive = research.get("adaptive") or {}
    regime = (adaptive.get("feature_11_regime") or {}).get("state", "UNAVAILABLE")
    expected = {"UPTREND": "BUY", "DOWNTREND": "SELL"}.get(regime)

    def lane(side):
        if side not in ("BUY", "SELL"):
            return {"side": side or "WAIT", "alignment": "NO_DIRECTION"}
        if expected is None:
            return {"side": side, "alignment": "REGIME_UNCERTAIN"}
        return {"side": side, "alignment": "ALIGNED" if side == expected else "COUNTER_REGIME"}

    official = lane(decision.get("side"))
    quick_lane = lane((quick or {}).get("side"))
    return {
        "regime": regime,
        "regime_direction": expected,
        "official": official,
        "quick": quick_lane,
        "lanes_disagree": (
            official["side"] in ("BUY", "SELL")
            and quick_lane["side"] in ("BUY", "SELL")
            and official["side"] != quick_lane["side"]
        ),
        "research_only": True,
    }
