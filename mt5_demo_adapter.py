"""Broker-neutral MT5 demo adapter contract.

No credentials, network calls, or live-account execution are implemented here.
A future Windows/MT5 EA transport must implement BrokerPort.
"""
from dataclasses import dataclass
from typing import Protocol
from execution_bridge import ExecutionPolicy, idempotency_key, validate_signal

@dataclass(frozen=True)
class OrderRequest:
    key: str
    symbol: str
    side: str
    volume: float
    stop_loss: float
    take_profit: float

class BrokerPort(Protocol):
    def account_is_demo(self) -> bool: ...
    def open_positions(self, symbol: str) -> int: ...
    def submit_market(self, request: OrderRequest) -> dict: ...
    def close_position(self, ticket: str) -> dict: ...

class MT5DemoAdapter:
    def __init__(self, broker: BrokerPort, policy=ExecutionPolicy()):
        self.broker=broker
        self.policy=policy
        self.executed=set()

    def prepare(self, signal, volume):
        ok,reason=validate_signal(
            signal,
            account_is_demo=self.broker.account_is_demo(),
            open_positions=self.broker.open_positions("XAUUSD"),
            policy=self.policy,
        )
        if not ok: return None,reason
        if not isinstance(volume,(int,float)) or volume<=0:
            return None,"invalid_volume"
        key=idempotency_key(signal)
        if key in self.executed: return None,"duplicate_order"
        req=OrderRequest(key,"XAUUSD",signal["side"],float(volume),
                         float(signal["sl"]),float(signal["tp1"]))
        return req,"approved"

    def execute(self, signal, volume):
        req,reason=self.prepare(signal,volume)
        if req is None: return {"ok":False,"reason":reason}
        result=self.broker.submit_market(req)
        if result.get("ok") is True:
            self.executed.add(req.key)
        return result
