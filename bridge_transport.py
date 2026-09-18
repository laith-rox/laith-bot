"""Minimal authenticated command queue for the isolated Laith DEMO bridge.

Transport-agnostic core: a future HTTPS service may call these methods.
No broker credentials and no live execution are present here.
"""
from dataclasses import dataclass
import time
from bridge_auth import sign, verify

@dataclass
class Pending:
    payload: dict
    signature: str
    delivered: bool=False
    ack: dict|None=None

class DemoCommandQueue:
    def __init__(self, secret):
        if not secret: raise ValueError("bridge_secret_required")
        self.secret=secret
        self.items={}

    def publish(self, payload):
        if payload.get("mode")!="DEMO": raise ValueError("demo_only")
        key=payload.get("key")
        if not key: raise ValueError("idempotency_key_required")
        if key in self.items: return {"ok":False,"reason":"duplicate_order","key":key}
        self.items[key]=Pending(payload=dict(payload),signature=sign(payload,self.secret))
        return {"ok":True,"key":key}

    def next(self, now=None):
        clock=time.time() if now is None else float(now)
        for key,item in self.items.items():
            if item.delivered or item.ack is not None: continue
            ok,reason=verify(item.payload,item.signature,self.secret,now=clock)
            if not ok:
                item.ack={"ok":False,"reason":reason}
                continue
            item.delivered=True
            return {"payload":item.payload,"signature":item.signature}
        return None

    def acknowledge(self,key,result):
        item=self.items.get(key)
        if item is None: return {"ok":False,"reason":"unknown_order"}
        if item.ack is not None: return {"ok":False,"reason":"already_acknowledged"}
        item.ack=dict(result)
        return {"ok":True,"key":key}
