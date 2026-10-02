import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RELAY_TOKEN = os.getenv("RELAY_TOKEN")
PORT = int(os.getenv("PORT", "8080"))

_recent = []
_recent_set = set()
MAX_RECENT = 256

def remember(event_id):
    if event_id in _recent_set:
        return False
    _recent.append(event_id)
    _recent_set.add(event_id)
    if len(_recent) > MAX_RECENT:
        old = _recent.pop(0)
        _recent_set.discard(old)
    return True

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("telegram_not_configured")
    body = urlencode({"chat_id": CHAT_ID, "text": text}).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(req, timeout=12) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError("telegram_send_failed")
    return payload

class Handler(BaseHTTPRequestHandler):
    server_version = "LaithLiveSignalRelay/1.0"

    def _json(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {
                "ok": True,
                "telegram_configured": bool(TOKEN and CHAT_ID),
                "relay_token_configured": bool(RELAY_TOKEN),
            })
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path != "/signal":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        if not RELAY_TOKEN or self.headers.get("X-Relay-Token") != RELAY_TOKEN:
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(payload.get("text") or "").strip()
            if not text:
                self._json(400, {"ok": False, "error": "missing_text"})
                return
            event_id = str(payload.get("event_id") or hashlib.sha256(text.encode("utf-8")).hexdigest())
            if not remember(event_id):
                self._json(200, {"ok": True, "duplicate": True})
                return
            send_telegram(text)
            self._json(200, {"ok": True, "duplicate": False})
        except Exception as exc:
            self._json(502, {"ok": False, "error": type(exc).__name__})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    if not TOKEN or not CHAT_ID or not RELAY_TOKEN:
        raise SystemExit("missing required relay configuration")
    print(f"live-signal-relay listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
