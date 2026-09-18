"""Authenticated command envelope for Laith demo bridge.

The shared secret belongs on the future bridge service and Windows/MT5 side only.
Never place it in Telegram messages or source control.
"""
import hashlib, hmac, json, time

MAX_AGE_SECONDS=30

def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def sign(payload,secret):
    return hmac.new(secret.encode(),canonical(payload),hashlib.sha256).hexdigest()

def verify(payload,signature,secret,now=None,max_age=MAX_AGE_SECONDS):
    if not isinstance(payload,dict) or not isinstance(signature,str): return False,"invalid_envelope"
    if payload.get("mode")!="DEMO": return False,"non_demo_command"
    ts=payload.get("ts")
    if not isinstance(ts,(int,float)): return False,"missing_timestamp"
    clock=time.time() if now is None else float(now)
    if abs(clock-float(ts))>max_age: return False,"stale_command"
    expected=sign(payload,secret)
    if not hmac.compare_digest(expected,signature): return False,"bad_signature"
    return True,"approved"

def order_payload(request,ts=None):
    return {"mode":"DEMO","ts":time.time() if ts is None else float(ts),
            "key":request.key,"symbol":request.symbol,"side":request.side,
            "volume":request.volume,"sl":request.stop_loss,"tp":request.take_profit}
