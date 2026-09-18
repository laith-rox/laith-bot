"""Isolated Laith demo execution gate. Not imported by the live bot."""
from dataclasses import dataclass
import hashlib, json

@dataclass(frozen=True)
class ExecutionPolicy:
    demo_only: bool=True
    max_open_positions: int=1
    allow_forced_bias: bool=False

def validate_signal(signal, account_is_demo, open_positions=0, policy=ExecutionPolicy()):
    if policy.demo_only and not account_is_demo: return False,"live_account_blocked"
    if open_positions>=policy.max_open_positions: return False,"position_limit"
    side=signal.get("side")
    if side not in ("BUY","SELL"): return False,"no_trade_direction"
    if signal.get("forced",True) and not policy.allow_forced_bias: return False,"best_available_bias_blocked"
    if signal.get("sl") is None: return False,"stop_required"
    if signal.get("tp1") is None: return False,"target_required"
    checks=signal.get("checks",{}).get(side,[])
    if len(checks)!=7 or sum(bool(x) for x in checks)<6: return False,"strict_conditions_not_met"
    return True,"approved"

def idempotency_key(signal):
    raw=json.dumps({k:signal.get(k) for k in ("id","side","bar","price_time")},sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:24]
