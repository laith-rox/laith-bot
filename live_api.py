"""Read-only XAU/USD feed for Laith Trading. No trade execution."""
import json, os, time, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import websocket
from market import Market, DataError

KEY=os.environ.get("TWELVE_DATA_API_KEY","")
PORT=int(os.environ.get("PORT","8080"))
market=Market(KEY)
tick={"price":None,"time":0.0,"source":None}
tick_lock=threading.Lock()
bars_cache={"at":0.0,"bars":[]}
rest_quote_cache={"at":0.0,"quote":None}

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

def get_bars(now):
    mono=time.monotonic()
    if bars_cache["bars"] and mono-bars_cache["at"]<55:
        return bars_cache["bars"]
    bars=market.fetch(now)[-180:]
    out=[{"t":int(b.start.timestamp()),"o":b.open,"h":b.high,"l":b.low,"c":b.close} for b in bars]
    bars_cache.update(at=mono,bars=out)
    return out

def get_quote(now):
    with tick_lock: q=dict(tick)
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

def snapshot():
    now=datetime.now(timezone.utc)
    q=get_quote(now)
    return {"ok":True,"symbol":"XAU/USD","price":q["price"],"quoteTime":q["time"],
      "source":q["source"],"bars":get_bars(now),"serverTime":int(now.timestamp()),"execution":False}

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
        except DataError as e:
            self._headers(503); self.wfile.write(json.dumps({"ok":False,"error":str(e),"execution":False}).encode())
        except Exception:
            self._headers(503); self.wfile.write(b'{"ok":false,"error":"feed_unavailable","execution":false}')
    def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args),flush=True)

if __name__=="__main__":
    if not KEY: raise SystemExit("TWELVE_DATA_API_KEY required")
    threading.Thread(target=ws_worker,daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
