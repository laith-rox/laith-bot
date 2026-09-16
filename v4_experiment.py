"""Versioned experiment identity for the independent Laith V4 bot."""
from copy import deepcopy
import hashlib
import json

from v3_experiment import V3_EXPERIMENT


V4_EXPERIMENT = deepcopy(V3_EXPERIMENT)
V4_EXPERIMENT.update({
    "name": "laith-v4-independent-paper-v1",
    "generation": "V4",
    "origin": "V3 validated research snapshot",
    "mode": "paper_only",
    "isolation": {
        "database": "/data/laith_v4.db",
        "telegram": False,
        "broker_orders": False,
        "live_bot_writes": False,
    },
})


def experiment_id(config=None):
    config = config or V4_EXPERIMENT
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def experiment_record(config=None):
    config = config or V4_EXPERIMENT
    return {"id": experiment_id(config), "config": config}
