"""Experiment identity and audit helpers for V3 research.

Every paper trade must be attributable to the exact rule set that produced it.
Changing a threshold creates a different deterministic experiment id, preventing
results from incompatible rule versions from being silently pooled.
"""
import hashlib
import json


V3_EXPERIMENT = {
    "name": "laith-v3-global-filter-v1",
    "baseline": "engine.analyze",
    "forced_bias": "reject",
    "sessions": {
        "allowed": ["ASIA", "LONDON", "NEW_YORK", "LONDON_NEW_YORK_OVERLAP"],
        "blocked": ["OTHER"],
    },
    "volatility": {
        "source": "15m_ATR_percentile",
        "lookback_bars": 96,
        "block_at_or_above_percentile": 95,
    },
    "macro": {
        "series": ["DTWEXBGS", "DGS10", "DFII10", "VIXCLS", "DCOILWTICO"],
        "asof_rule": "previous_calendar_day_or_earlier",
        "veto": "STRONG_CONFLICT_only",
        "oil_directional_vote": False,
    },
    "event_guard": {
        "source": "existing_high_impact_USD_calendar",
        "before_minutes": 15,
        "after_minutes": 30,
    },
    "execution": {
        "decision": "closed_candles_only",
        "entry_quote": "timestamped_provider_rate",
        "max_quote_age_seconds": 90,
        "cooldown_minutes": 60,
    },
}


def experiment_id(config=None):
    config = config or V3_EXPERIMENT
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def experiment_record(config=None):
    config = config or V3_EXPERIMENT
    return {"id": experiment_id(config), "config": config}
