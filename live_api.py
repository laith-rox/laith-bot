"""Read-only XAU/USD feed for Laith Trading. No trade execution."""
import json, math, os, time, threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import requests
import websocket

from market import Market, DataError, Bar, closed_only
from gigi_gold_brain import GigiGoldBrain

KEY=os.environ.get("TWELVE_DATA_API_KEY","")
PORT=int(os.environ.get("PORT","8080"))
market=Market(KEY)
intelligence=GigiGoldBrain(KEY)
tick={"price":None,"time":0.0,"source":None}
tick_lock=threading.Lock()
rest_quote_cache={"at":0.0,"quote":None}
fallback_cache={"at":0.0,"bars":[]}
YAHOO_CHART="https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF"

def set_tick(price,stamp,source):
    try:
        p=float(price); ts=float(stamp)
        if p<=0 or ts<=0: return
        with tick_lock: tick.update(price=p,time=ts,source=source)
    except (TypeError,ValueError):
        return

def ws_worker():
    if not KEY: return
    url="wss://ws.twelvedata.com/v1/quotes/price?apikey="+KEY
    while True:
        ws=None
        try:
            def on_open(sock):
                sock.send(json.dumps({"action":"subscribe","params":{"symbols":"XAU/USD"}}))
            def on_message(sock,msg):
                try:
                    d=json.loads(msg)
                    if d.get("event")=="price" and d.get("symbol")=="XAU/USD":
                        set_tick(d.get("price"),d.get("timestamp"),"Twelve Data WebSocket")
                except Exception:
                    pass
            ws=websocket.WebSocketApp(url,on_open=on_open,on_message=on_message)
            ws.run_forever(ping_interval=20,ping_timeout=10)
        except Exception:
            pass
        finally:
            try:
                if ws: ws.close()
            except Exception: pass
        time.sleep(5)

def serialize_bars(bars):
    return [{"t":int(b.start.timestamp()),"o":b.open,"h":b.high,"l":b.low,"c":b.close} for b in bars[-180:]]

def get_quote(now):
    with tick_lock: q=dict(tick)
    if q["price"] and 0<=now.timestamp()-q["time"]<=90:
        return q
    mono=time.monotonic()
    cached=rest_quote_cache["quote"]
    if cached and mono-rest_quote_cache["at"]<55:
        return cached
    rq=market.quote(lambda: now)
    q={"price":rq["price"],"time":rq["time"],"source":"Twelve Data REST"}
    rest_quote_cache.update(at=mono,quote=q)
    return q

def _yahoo_payload_to_bars(payload,spot_price,now):
    try:
        result=payload["chart"]["result"][0]
        stamps=result["timestamp"]
        quote=result["indicators"]["quote"][0]
        opens=quote["open"]; highs=quote["high"]; lows=quote["low"]; closes=quote["close"]
    except (KeyError,IndexError,TypeError):
        raise DataError("fallback_response_invalid") from None

    raw=[]
    for ts,o,h,l,c in zip(stamps,opens,highs,lows,closes):
        if None in (ts,o,h,l,c): continue
        try:
            ts=int(ts); o=float(o); h=float(h); l=float(l); c=float(c)
        except (TypeError,ValueError,OverflowError):
            continue
        vals=(o,h,l,c)
        if ts%300 or not all(math.isfinite(v) and v>0 for v in vals): continue
        dt=datetime.fromtimestamp(ts,timezone.utc)
        if dt>now+timedelta(seconds=5) or not l<=min(o,c)<=max(o,c)<=h: continue
        raw.append(Bar(dt,o,h,l,c,5))

    raw=sorted({b.start:b for b in raw}.values(),key=lambda b:b.start)
    if len(raw)<1200:
        raise DataError("fallback_insufficient_history")

    basis=float(spot_price)-raw[-1].close
    shifted=[
        Bar(b.start,b.open+basis,b.high+basis,b.low+basis,b.close+basis,5)
        for b in raw
    ]
    shifted=closed_only(shifted,now)
    if len(shifted)<1200:
        raise DataError("fallback_insufficient_closed_history")
    return shifted

def _fallback_bars(spot_price,now):
    mono=time.monotonic()
    if fallback_cache["bars"] and mono-fallback_cache["at"]<240:
        return fallback_cache["bars"]
    try:
        response=requests.get(
            YAHOO_CHART,
            params={"interval":"5m","range":"5d","includePrePost":"true","events":"div,splits"},
            headers={"User-Agent":"Mozilla/5.0 LaithTrading/1.0"},
            timeout=(5,15),
        )
        if response.status_code!=200:
            raise DataError("fallback_http_%s"%response.status_code)
        bars=_yahoo_payload_to_bars(response.json(),spot_price,now)
    except DataError:
        raise
    except Exception:
        raise DataError("fallback_unavailable") from None
    fallback_cache.update(at=mono,bars=bars)
    return bars

def _apply_analysis(payload,full_bars,now,data_quality):
    payload["bars"]=serialize_bars(full_bars)
    try:
        payload.update(intelligence.snapshot(full_bars,now))
        payload["analysisAvailable"]=True
        payload["analysisDataQuality"]=data_quality
        gigi=payload.get("gigi")
        if isinstance(gigi,dict):
            gigi["executionEligible"]=False
            if data_quality=="FALLBACK_APPROXIMATE":
                gigi["dataQuality"]="FALLBACK_APPROXIMATE"
                gigi["confidenceScore"]=min(int(gigi.get("confidenceScore",0)),65)
                gigi["confidenceMeaning"]="alignment_score_capped_due_to_basis_adjusted_futures"
            else:
                gigi["dataQuality"]="PRIMARY_SPOT_BARS"
    except Exception as exc:
        payload["intelligenceError"]=str(exc)[:100]

def snapshot():
    now=datetime.now(timezone.utc)
    payload={
        "ok":True,"symbol":"XAU/USD","price":None,"quoteTime":None,"source":None,
        "bars":[],"serverTime":int(now.timestamp()),"execution":False,
        "analysisAvailable":False,"fallbackUsed":False,
    }

    try:
        q=get_quote(now)
        payload.update(price=q["price"],quoteTime=q["time"],source=q["source"])
    except DataError as exc:
        payload["quoteError"]=str(exc)[:100]

    try:
        full_bars=market.fetch(now)
        state=market.status()
        payload["marketData"]={**state,"available":True}
        payload["analysisDataSource"]="Twelve Data XAU/USD 5m"
        _apply_analysis(payload,full_bars,now,"PRIMARY")
        if state.get("barsStale") and isinstance(payload.get("gigi"),dict):
            payload["analysis"]["entryReady"]=False
            payload["analysis"]["side"]="WAIT"
            payload["gigi"]["entryReady"]=False
            payload["gigi"]["side"]="WAIT"
            payload["gigi"]["decision"]="WAIT_DATA"
            payload["gigi"]["reason"]="market_data_stale"
            payload["gigi"]["confidenceScore"]=min(int(payload["gigi"].get("confidenceScore",0)),35)
    except DataError as exc:
        state=market.status()
        payload["marketData"]={**state,"available":False,"error":str(exc)[:100]}
        if payload["price"] is not None:
            try:
                full_bars=_fallback_bars(payload["price"],now)
                payload["fallbackUsed"]=True
                payload["analysisDataSource"]="Yahoo GC=F 5m, basis-adjusted to live XAU/USD quote"
                payload["primaryBarsError"]=str(exc)[:100]
                _apply_analysis(payload,full_bars,now,"FALLBACK_APPROXIMATE")
            except DataError as fallback_exc:
                payload["fallbackError"]=str(fallback_exc)[:100]

    payload["ok"]=bool(payload["price"] is not None or payload["bars"])
    return payload

class H(BaseHTTPRequestHandler):
    def _headers(self,status=200):
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Access-Control-Allow-Origin","https://laith-app-production.up.railway.app")
        self.send_header("Vary","Origin")
        self.end_headers()
    def do_OPTIONS(self): self._headers(204)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=="/":
            self._headers(); self.wfile.write(b'{"ok":true,"service":"gold-feed","execution":false}'); return
        if p!="/api/gold":
            self._headers(404); self.wfile.write(b'{"ok":false,"error":"not_found"}'); return
        try:
            self._headers(); self.wfile.write(json.dumps(snapshot(),separators=(",",":")).encode())
        except Exception:
            self._headers(503); self.wfile.write(b'{"ok":false,"error":"feed_unavailable","execution":false}')
    def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args),flush=True)

if __name__=="__main__":
    if not KEY: raise SystemExit("TWELVE_DATA_API_KEY required")
    threading.Thread(target=ws_worker,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
