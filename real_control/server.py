from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
import threading
import time
from urllib.parse import urlparse

PORT = int(os.getenv("PORT", "8080"))
ARMING_ALLOWED = os.getenv("REAL_CONTROL_ARMING_ALLOWED", "false").strip().lower() == "true"
OWNER_TOKEN = os.getenv("REAL_CONTROL_OWNER_TOKEN", "").strip()

_lock = threading.Lock()
_state = {
    "armed": False,
    "emergency_stop": True,
    "execution_enabled": False,
    "updated_at": time.time(),
}


def _status():
    with _lock:
        return {
            "ok": True,
            "mode": "REAL",
            "locked": not ARMING_ALLOWED,
            "arming_allowed": ARMING_ALLOWED,
            "armed": bool(_state["armed"]),
            "emergency_stop": bool(_state["emergency_stop"]),
            "execution_enabled": bool(_state["execution_enabled"]),
            "owner_auth_configured": bool(OWNER_TOKEN),
            "trade_endpoint_present": False,
            "updated_at": _state["updated_at"],
        }


def _authorized(handler) -> bool:
    if not OWNER_TOKEN:
        return False
    supplied = handler.headers.get("X-Owner-Token", "")
    return hmac.compare_digest(supplied, OWNER_TOKEN)


ALLOWED_ORIGIN = os.getenv(
    "REAL_CONTROL_ALLOWED_ORIGIN",
    "https://laith-app-production.up.railway.app",
).strip()


def _cors(handler):
    origin = handler.headers.get("Origin", "")
    if ALLOWED_ORIGIN and origin == ALLOWED_ORIGIN:
        handler.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        handler.send_header("Vary", "Origin")


def _json(handler, status, payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    _cors(handler)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "LaithRealControl/1.0"

    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        self.send_response(204)
        _cors(self)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Owner-Token")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health", "/status"):
            return _json(self, 200, _status())
        return _json(self, 404, {"ok": False, "reason": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/arm", "/disarm", "/emergency-stop"):
            return _json(self, 404, {"ok": False, "reason": "not_found"})
        if not _authorized(self):
            return _json(self, 401, {"ok": False, "reason": "owner_auth_required"})

        global _state
        with _lock:
            if path == "/arm":
                if not ARMING_ALLOWED:
                    return _json(self, 423, {"ok": False, "reason": "real_control_locked"})
                # This service never enables order execution by itself.
                _state["armed"] = True
                _state["emergency_stop"] = True
                _state["execution_enabled"] = False
            elif path == "/disarm":
                _state["armed"] = False
                _state["emergency_stop"] = True
                _state["execution_enabled"] = False
            else:
                _state["armed"] = False
                _state["emergency_stop"] = True
                _state["execution_enabled"] = False
            _state["updated_at"] = time.time()
        return _json(self, 200, _status())


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
