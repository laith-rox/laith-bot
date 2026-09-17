"""Laith V4 decision adapter.

V4 starts from the validated V3 research snapshot copied into the v4-main branch,
then exposes a V4-only contract so future V4 changes cannot alter the live bot or
V3 paper worker.
"""
from v3_research import analyze_v3
from v4_intelligence import enrich_decision


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
    result["v4"] = research
    return enrich_decision(result, bars, now)
