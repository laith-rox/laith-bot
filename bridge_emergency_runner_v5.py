"""DEMO-only emergency runner v5. Activates existing emergency evaluation without opening trades."""
import urllib.request
BASE="https://raw.githubusercontent.com/laith-rox/laith-bot/9dbbb96e8ddc99f9c0f11e2e047afd0b273c4157/bridge_emergency_worker.py"
ns={"__name__":"bridge_emergency_base"}
exec(compile(urllib.request.urlopen(BASE,timeout=15).read(),BASE,"exec"),ns)
import time
from collections import deque

def run_forever():
    ns["validate_config"]()
    tracked={}
    ticks=0
    POLL=ns["POLL"]; WINDOW=ns["WINDOW"]; CONFIRM=ns["CONFIRM"]; HEARTBEAT_EVERY=ns["HEARTBEAT_EVERY"]
    print(f"bridge_emergency_started version=5.0 poll={POLL}s emergency_auto_close=true mode=DEMO_ONLY",flush=True)
    while True:
        try:
            status,health=ns["req"]("/health")
            if status!=200 or health.get("mode")!="DEMO" or not health.get("client_state_fresh"):
                tracked.clear(); time.sleep(POLL); continue
            positions=health.get("positions")
            if not isinstance(positions,list) or not positions:
                positions=[health] if health.get("position_open") and health.get("position_owned") else []
            owned=[p for p in positions if bool(p.get("owned",p.get("position_owned",False)))]
            live={str(p.get("ticket") or "") for p in owned}
            for stale in list(tracked):
                if stale not in live: tracked.pop(stale,None)
            for p in owned:
                ticket=str(p.get("ticket") or ""); side=str(p.get("side") or "").upper()
                try:
                    price=float(p.get("price") or health.get("price") or 0); stop=float(p.get("sl") or 0)
                    entry=float(p.get("open_price") or 0); tp=float(p.get("tp") or 0); profit=float(p.get("profit") or 0)
                except (TypeError,ValueError): continue
                if not ticket or side not in ("BUY","SELL") or min(price,stop,entry)<=0: continue
                s=tracked.setdefault(ticket,{"peak":max(0.0,profit),"prices":deque(maxlen=WINDOW),"profits":deque(maxlen=WINDOW),"confirm":0,"last_reason":None,"last_requested_sl":None})
                s["peak"]=max(float(s["peak"]),profit); s["prices"].append(price); s["profits"].append(profit)
                target_sl=ns["insured_sl"](side,entry,stop,s["peak"])
                if target_sl is not None:
                    valid=target_sl<price if side=="BUY" else target_sl>price
                    if valid and (s["last_requested_sl"] is None or abs(target_sl-s["last_requested_sl"])>=0.05):
                        code,response=ns["manage_modify"](ticket,target_sl,tp,"entry_insurance")
                        print(f"bridge_entry_insurance_modify ticket={ticket} side={side} profit={profit:.2f} peak={s['peak']:.2f} old_sl={stop:.2f} new_sl={target_sl:.2f} http={code}",flush=True)
                        if code==201 and response.get("ok") is True: s["last_requested_sl"]=target_sl
                reason,hard=ns["evaluate_profit_guardian"](p,s["prices"],s["profits"],s["peak"])
                if not reason: reason,hard=ns["evaluate_emergency"](p,s["prices"])
                if reason:
                    if hard: s["confirm"]=CONFIRM
                    elif reason==s["last_reason"]: s["confirm"]+=1
                    else: s["confirm"]=1
                    s["last_reason"]=reason
                    print(f"bridge_emergency_detected ticket={ticket} side={side} profit={profit:.2f} reason={reason} confirm={s['confirm']}/{CONFIRM} hard={hard}",flush=True)
                    if s["confirm"]>=CONFIRM:
                        code,response=ns["manage_close"](ticket,reason)
                        print(f"bridge_emergency_close_requested ticket={ticket} reason={reason} http={code} response={response}",flush=True)
                        s["confirm"]=0
                else:
                    s["confirm"]=0; s["last_reason"]=None
                ticks+=1
                if ticks%HEARTBEAT_EVERY==0:
                    print(f"bridge_emergency_heartbeat ticket={ticket} side={side} profit={profit:.2f} peak={s['peak']:.2f} samples={len(s['prices'])}",flush=True)
        except Exception as exc:
            print(f"bridge_emergency_error type={type(exc).__name__} detail={exc}",flush=True)
        time.sleep(POLL)

if __name__=="__main__":
    run_forever()
