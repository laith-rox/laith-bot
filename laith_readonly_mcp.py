import json, os, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.getenv("LAITH_READ_URL", "https://bridge-api-production-5b7b.up.railway.app/chatgpt-read")
PORT = int(os.getenv("PORT", "8080"))

def upstream():
    req=urllib.request.Request(UPSTREAM,headers={"User-Agent":"Laith-ChatGPT-MCP/1.0"})
    with urllib.request.urlopen(req,timeout=8) as r:
        return json.loads(r.read().decode())

def rpc_result(i,result):
    return {"jsonrpc":"2.0","id":i,"result":result}

class H(BaseHTTPRequestHandler):
    def out(self,status,obj,ctype="application/json"):
        b=json.dumps(obj,separators=(",",":")).encode()
        self.send_response(status); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path in ("/","/health"):
            return self.out(200,{"ok":True,"service":"laith-trading-readonly-mcp","mode":"DEMO_ONLY","mutations":False})
        return self.out(404,{"ok":False})
    def do_POST(self):
        if self.path!="/mcp": return self.out(404,{"ok":False})
        try:
            n=int(self.headers.get("Content-Length","0")); q=json.loads(self.rfile.read(n) or b"{}"); i=q.get("id"); m=q.get("method")
            if m=="initialize":
                return self.out(200,rpc_result(i,{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"laith-trading-readonly","version":"1.0.0"}}))
            if m=="notifications/initialized":
                self.send_response(202); self.end_headers(); return
            if m=="tools/list":
                return self.out(200,rpc_result(i,{"tools":[{"name":"get_demo_gold_snapshot","description":"Read the current sanitized XAUUSD DEMO market/account snapshot. Read-only; cannot place, close, or modify trades.","inputSchema":{"type":"object","properties":{},"additionalProperties":False}}]}))
            if m=="tools/call":
                p=q.get("params") or {}
                if p.get("name")!="get_demo_gold_snapshot":
                    return self.out(200,{"jsonrpc":"2.0","id":i,"error":{"code":-32602,"message":"Unknown tool"}})
                d=upstream()
                return self.out(200,rpc_result(i,{"content":[{"type":"text","text":json.dumps(d,separators=(",",":"))}],"structuredContent":d,"isError":False}))
            return self.out(200,{"jsonrpc":"2.0","id":i,"error":{"code":-32601,"message":"Method not found"}})
        except Exception as e:
            return self.out(200,{"jsonrpc":"2.0","id":None,"error":{"code":-32000,"message":"Read-only upstream unavailable"}})
    def log_message(self,fmt,*args): print("mcp_http",fmt%args,flush=True)

ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
