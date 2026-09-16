"""Experiment identity and audit helpers for V3 research.

Every paper trade must be attributable to the exact rule set that produced it.
Changing a threshold or data source creates a different deterministic experiment
id, preventing results from incompatible rule versions from being silently pooled.
"""
import hashlib
import json


V3_EXPERIMENT = {
    "name": "laith-v3-structure-lab-v3",
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
        "primary_source": ["DTWEXBGS", "DGS10", "DFII10", "VIXCLS", "DCOILWTICO"],
        "runtime_fallback": ["UUP", "TLT", "VIXY", "SPY", "USO"],
        "fallback_label": "twelve_proxy",
        "asof_rule": "previous_calendar_day_or_earlier",
        "veto": "STRONG_CONFLICT_only",
        "oil_directional_vote": False,
        "proxy_equity_directional_vote": False,
    },
    "price_structure": {
        "pivot_confirmation": "2_left_2_right_closed_bars",
        "timeframes": ["15m", "1h"],
        "zone_half_width_atr": 0.18,
        "break_confirmation": "two_15m_closes_plus_0.10_ATR_buffer",
        "failed_break": "wick_through_zone_then_close_back_inside",
        "block_failed_break_against_entry": True,
        "block_strong_triggered_correction": True,
    },
    "correction_map": {
        "source": "last_confirmed_impulse_plus_structural_zones",
        "strength": "rule_completion_not_probability",
        "reference_retracements": [0.382, 0.5, 0.618],
        "primary_targets": "confirmed_structural_zones",
    },
    "risk": {
        "stop": "beyond_nearest_structural_invalidation_plus_0.18_ATR",
        "minimum_stop_atr": 0.65,
        "maximum_stop_atr": 2.20,
        "minimum_room_to_opposing_structure_R": 1.15,
        "tp1_R": 1.40,
        "tp2_R": 2.20,
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
