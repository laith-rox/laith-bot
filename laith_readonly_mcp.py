import json, os, urllib.request, time\nfrom datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM=os.getenv("LAITH_READ_URL","https://bridge-api-production-5b7b.up.railway.app/chatgpt-read")
PORT=int(os.getenv("PORT","8080"))
def upstream():
    req=urllib.request.Request(UPSTREAM,headers={"User-Agent":"Laith-ChatGPT-MCP/1.0"})
    with urllib.request.urlopen(req,timeout=8) as r:return json.loads(r.read().decode())
def reference_bars():
    # Directional reference only. This never replaces the broker/MT5 spot price.
    u="https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=5m&range=5d"
    req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=8) as r:d=json.loads(r.read().decode())
    z=d["chart"]["result"][0]; ts=z["timestamp"]; q=z["indicators"]["quote"][0]
    rows=[]
    for i,t in enumerate(ts):
        try:
            vals=[q[k][i] for k in ("open","high","low","close")]
            if any(v is None for v in vals):continue
            rows.append({"datetime":datetime.fromtimestamp(int(t),tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                         "open":round(float(vals[0]),2),"high":round(float(vals[1]),2),
                         "low":round(float(vals[2]),2),"close":round(float(vals[3]),2)})
        except (IndexError,TypeError,ValueError):continue
    if not rows:raise RuntimeError("reference_bars_unavailable")
    last=rows[-1]
    try:age=max(0,time.time()-datetime.strptime(last["datetime"],"%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc).timestamp())
    except Exception:age=None
    return {"symbol":"GC=F","purpose":"directional_reference_only","interval":"5m",
            "latest":last,"recent":rows[-12:],"age_seconds":round(age,1) if age is not None else None,
            "fresh":age is not None and age<=900}
def snapshot():
    d=upstream()
    try:d["reference_market"]=reference_bars()
    except Exception:d["reference_market"]={"symbol":"GC=F","purpose":"directional_reference_only","fresh":False,"error":"reference_unavailable"}
    d["latest_source_note"]="latest.m5/m15/h1 are legacy MT5 market publisher fields; use reference_market only when fresh for directional candle context"
    return d
def rr(i,r):return {"jsonrpc":"2.0","id":i,"result":r}
class H(BaseHTTPRequestHandler):
    def out(self,s,o):
        b=json.dumps(o,separators=(",",":")).encode();self.send_response(s);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        self.out(200,{"ok":True,"service":"laith-trading-readonly-mcp","mode":"DEMO_ONLY","mutations":False}) if self.path in ("/","/health") else self.out(404,{"ok":False})
    def do_POST(self):
        if self.path!="/mcp":return self.out(404,{"ok":False})
        try:
            n=int(self.headers.get("Content-Length","0"));q=json.loads(self.rfile.read(n) or b"{}");i=q.get("id");m=q.get("method")
            if m=="initialize":return self.out(200,rr(i,{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"laith-trading-readonly","version":"1.0.0"}}))
            if m=="notifications/initialized":self.send_response(202);self.end_headers();return
            if m=="tools/list":return self.out(200,rr(i,{"tools":[{"name":"get_demo_gold_snapshot","description":"Read current sanitized XAUUSD DEMO snapshot. Read-only; cannot place, close, or modify trades.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}}]}))
            if m=="tools/call":
                if (q.get("params") or {}).get("name")!="get_demo_gold_snapshot":return self.out(200,{"jsonrpc":"2.0","id":i,"error":{"code":-32602,"message":"Unknown tool"}})
                d=snapshot();return self.out(200,rr(i,{"content":[{"type":"text","text":json.dumps(d,separators=(",",":"))}],"structuredContent":d,"isError":False}))
            return self.out(200,{"jsonrpc":"2.0","id":i,"error":{"code":-32601,"message":"Method not found"}})
        except Exception:return self.out(200,{"jsonrpc":"2.0","id":None,"error":{"code":-32000,"message":"Read-only upstream unavailable"}})
    def log_message(self,f,*a):print("mcp_http",f%a,flush=True)
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
