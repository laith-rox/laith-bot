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
primary_bars_backoff={"until":0.0,"error":None}
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
            except Exception:
                pass
        time.sleep(5)


def get_quote(now):
    with tick_lock:
        q=dict(tick)
    if q["price"] and 0<=now.timestamp()-q["time"]<=90:
        return q
    mono=time.monotonic()
    cached=rest_quote_cache["quote"]
    if cached and mono-rest_quote_cache["at"]<25:
        return cached
    rq=market.quote(lambda: now)
    q={"price":rq["price"],"time":rq["time"],"source":"Twelve Data REST"}
    rest_quote_cache.update(at=mono,quote=q)
    return q


def _yahoo_payload_to_bars(payload, spot_price, now):
    try:
        result=payload["chart"]["result"][0]
        stamps=result["timestamp"]
        quote=result["indicators"]["quote"][0]
        opens=quote["open"]; highs=quote["high"]; lows=quote["low"]; closes=quote["close"]
    except (KeyError,IndexError,TypeError):
        raise DataError("fallback_response_invalid") from None

    raw=[]
    for ts,o,h,l,c in zip(stamps,opens,highs,lows,closes):
        if None in (ts,o,h,l,c):
            continue
        try:
            ts=int(ts); o=float(o); h=float(h); l=float(l); c=float(c)
        except (TypeError,ValueError,OverflowError):
            continue
        vals=(o,h,l,c)
        if ts%300 or not all(math.isfinite(v) and v>0 for v in vals):
            continue
        dt=datetime.fromtimestamp(ts,timezone.utc)
        if dt>now+timedelta(seconds=5) or not l<=min(o,c)<=max(o,c)<=h:
            continue
        raw.append(Bar(dt,o,h,l,c,5))

    if len(raw)<1200:
        raise DataError("fallback_insufficient_history")

    raw.sort(key=lambda b:b.start)
    by_time={b.start:b for b in raw}
    raw=list(by_time.values())
    last=raw[-1].close
    basis=float(spot_price)-last
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
        r=requests.get(
            YAHOO_CHART,
            params={"interval":"5m","range":"5d","includePrePost":"true","events":"div,splits"},
            headers={"User-Agent":"Mozilla/5.0 LaithTrading/1.0"},
            timeout=(5,15),
        )
        if r.status_code!=200:
            raise DataError("fallback_http_%s"%r.status_code)
        bars=_yahoo_payload_to_bars(r.json(),spot_price,now)
    except DataError:
        raise
    except Exception:
        raise DataError("fallback_unavailable") from None
    fallback_cache.update(at=mono,bars=bars)
    return bars


def get_analysis_bars(now,spot_price):
    mono=time.monotonic()
    if mono>=primary_bars_backoff["until"]:
        try:
            bars=market.fetch(now)
            primary_bars_backoff.update(until=0.0,error=None)
            return bars,False,"Twelve Data XAU/USD 5m",None
        except DataError as exc:
            err=str(exc)
            if "429" in err or "quota" in err:
                primary_bars_backoff.update(until=mono+300,error=err)
            else:
                primary_bars_backoff.update(until=mono+60,error=err)

    err=primary_bars_backoff["error"] or "primary_bars_backoff"
    bars=_fallback_bars(spot_price,now)
    return bars,True,"Yahoo GC=F 5m, basis-adjusted to live XAU/USD quote",err


def snapshot():
    now=datetime.now(timezone.utc)
    q=get_quote(now)
    full_bars,fallback_used,analysis_source,primary_error=get_analysis_bars(now,q["price"])
    out_bars=full_bars[-180:]
    payload={
        "ok":True,
        "symbol":"XAU/USD",
        "price":q["price"],
        "quoteTime":q["time"],
        "source":q["source"],
        "analysisDataSource":analysis_source,
        "fallbackUsed":fallback_used,
        "primaryBarsError":primary_error,
        "bars":[
            {"t":int(b.start.timestamp()),"o":b.open,"h":b.high,"l":b.low,"c":b.close}
            for b in out_bars
        ],
        "serverTime":int(now.timestamp()),
        "execution":False,
    }
    try:
        intel=intelligence.snapshot(full_bars,now)
        if fallback_used:
            gigi=intel.get("gigi")
            if isinstance(gigi,dict):
                gigi["dataQuality"]="FALLBACK_APPROXIMATE"
                gigi["confidenceScore"]=min(int(gigi.get("confidenceScore",0)),65)
                gigi["confidenceMeaning"]="alignment_score_capped_due_to_basis_adjusted_futures"
                gigi["executionEligible"]=False
            intel["analysisDataQuality"]="FALLBACK_APPROXIMATE"
        else:
            if isinstance(intel.get("gigi"),dict):
                intel["gigi"]["dataQuality"]="PRIMARY_SPOT_BARS"
                intel["gigi"]["executionEligible"]=False
            intel["analysisDataQuality"]="PRIMARY"
        payload.update(intel)
    except Exception as exc:
        payload["intelligenceError"]=str(exc)[:100]
    return payload


class H(BaseHTTPRequestHandler):
    def _headers(self,status=200):
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("Access-Control-Allow-Origin","https://laith-app-production.up.railway.app")
        self.send_header("Vary","Origin")
        self.end_headers()
    def do_OPTIONS(self):
        self._headers(204)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=="/":
            self._headers()
            self.wfile.write(b'{"ok":true,"service":"gold-feed","execution":false}')
            return
        if p!="/api/gold":
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"not_found"}')
            return
        try:
            body=json.dumps(snapshot(),separators=(",",":")).encode()
            self._headers(200)
            self.wfile.write(body)
        except DataError as e:
            self._headers(503)
            self.wfile.write(json.dumps({"ok":False,"error":str(e),"execution":False}).encode())
        except Exception:
            self._headers(503)
            self.wfile.write(b'{"ok":false,"error":"feed_unavailable","execution":false}')
    def log_message(self,fmt,*args):
        print("%s - %s"%(self.address_string(),fmt%args),flush=True)


if __name__=="__main__":
    if not KEY:
        raise SystemExit("TWELVE_DATA_API_KEY required")
    threading.Thread(target=ws_worker,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
