"""DEMO-only emergency manager for the isolated Laith execution bridge.

Uses fresh MT5 state reported by the EA. It never opens trades. It can only
close a bridge-owned XAUUSD DEMO position after persistent adverse movement.
"""
import json, os, time
from collections import deque
from urllib.request import Request, urlopen

BRIDGE_URL=os.environ["BRIDGE_URL"].rstrip("/")
TOKEN=os.environ["BRIDGE_PUBLISH_TOKEN"]
POLL=max(2,int(os.getenv("EMERGENCY_POLL_SECONDS","10")))
WINDOW=max(6,int(os.getenv("EMERGENCY_WINDOW","12")))
MIN_ADVERSE=float(os.getenv("EMERGENCY_MIN_ADVERSE_USD","1.20"))
CONFIRM=max(2,int(os.getenv("EMERGENCY_CONFIRM","3")))
prices=deque(maxlen=WINDOW)
last_ticket=""
pressure=0
close_requested_ticket=""

def req(path,method="GET",payload=None):
    data=None if payload is None else json.dumps(payload,separators=(",",":")).encode()
    h={"Accept":"application/json"}
    if payload is not None:
        h["Content-Type"]="application/json"; h["X-Publish-Token"]=TOKEN
    r=Request(BRIDGE_URL+path,data=data,method=method,headers=h)
    with urlopen(r,timeout=8) as x:
        raw=x.read().decode(); return x.status,(json.loads(raw) if raw else {})

def manage_close(ticket,reason):
    key=f"emg:{ticket}:{int(time.time())}"
    body={"mode":"DEMO","key":key,"symbol":"XAUUSD","action":"CLOSE","reason":reason}
    return req("/manage","POST",body)

print(f"bridge_emergency_started poll={POLL}s window={WINDOW} confirm={CONFIRM}",flush=True)
while True:
    try:
        status,h=req("/health")
        if status!=200 or h.get("mode")!="DEMO" or not h.get("client_state_fresh"):
            prices.clear(); pressure=0; time.sleep(POLL); continue
        if not h.get("position_open") or not h.get("position_owned"):
            prices.clear(); pressure=0; last_ticket=""; close_requested_ticket=""; time.sleep(POLL); continue
        ticket=str(h.get("ticket") or "")
        side=str(h.get("side") or "").upper()
        price=float(h.get("price") or 0); stop=float(h.get("sl") or 0)
        if not ticket or side not in ("BUY","SELL") or price<=0 or stop<=0:
            time.sleep(POLL); continue
        if ticket!=last_ticket:
            prices.clear(); pressure=0; last_ticket=ticket; close_requested_ticket=""
        if close_requested_ticket==ticket:
            time.sleep(POLL); continue
        prices.append(price)
        if len(prices)<6:
            time.sleep(POLL); continue
        direction=1 if side=="BUY" else -1
        adverse=direction*(prices[-1]-max(prices) if side=="BUY" else prices[-1]-min(prices))
        momentum=direction*(prices[-1]-prices[-4])
        stop_distance=direction*(price-stop)
        danger=(adverse<=-MIN_ADVERSE and momentum<0) or stop_distance<=0.35
        pressure=pressure+1 if danger else max(0,pressure-1)
        if pressure>=CONFIRM:
            code,res=manage_close(ticket,"v4_style_emergency_reversal")
            print(f"bridge_emergency_close ticket={ticket} http={code} response={res}",flush=True)
            if code==201 and res.get("ok") is True:
                close_requested_ticket=ticket
            pressure=0; prices.clear()
    except Exception as exc:
        print(f"bridge_emergency_error type={type(exc).__name__} detail={exc}",flush=True)
    time.sleep(POLL)
