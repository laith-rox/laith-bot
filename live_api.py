"""Read-only XAU/USD feed for Laith Trading app. No trade execution."""
import json, os, time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from market import Market, DataError

KEY=os.environ.get("TWELVE_DATA_API_KEY","")
PORT=int(os.environ.get("PORT","8080"))
market=Market(KEY)
_cache={"at":0.0,"data":None}

def snapshot():
    now=datetime.now(timezone.utc)
    # Protect provider quota while still allowing the UI to poll frequently.
    if _cache["data"] and time.monotonic()-_cache["at"] < 8:
        return _cache["data"]
    q=market.quote(lambda: now)
    bars=market.fetch(now)[-180:]
    data={
      "ok":True,"symbol":"XAU/USD","price":q["price"],
      "quoteTime":q["time"],"source":q["source"],
      "bars":[{"t":int(b.start.timestamp()),"o":b.open,"h":b.high,"l":b.low,"c":b.close} for b in bars],
      "serverTime":int(now.timestamp()),"execution":False
    }
    _cache.update(at=time.monotonic(),data=data)
    return data

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
            self._headers(); self.wfile.write(b'{"ok":true,"service":"gold-feed","execution":false}')
            return
        if p!="/api/gold":
            self._headers(404); self.wfile.write(b'{"ok":false,"error":"not_found"}'); return
        try:
            d=snapshot(); self._headers(); self.wfile.write(json.dumps(d,separators=(",",":")).encode())
        except DataError as e:
            self._headers(503); self.wfile.write(json.dumps({"ok":False,"error":str(e),"execution":False}).encode())
        except Exception:
            self._headers(503); self.wfile.write(b'{"ok":false,"error":"feed_unavailable","execution":false}')
    def log_message(self,fmt,*args):
        print("%s - %s"%(self.address_string(),fmt%args),flush=True)

if __name__=="__main__":
    if not KEY: raise SystemExit("TWELVE_DATA_API_KEY required")
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
