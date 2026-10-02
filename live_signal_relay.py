import hashlib
import hmac
import html
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RELAY_TOKEN = os.getenv("RELAY_TOKEN")
PORT = int(os.getenv("PORT", "8080"))
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "https://live-signal-relay-production.up.railway.app",
).rstrip("/")
APPROVAL_TTL_SECONDS = int(os.getenv("APPROVAL_TTL_SECONDS", "180"))
LEASE_SECONDS = int(os.getenv("APPROVAL_LEASE_SECONDS", "25"))

_recent = []
_recent_set = set()
_events = {}
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


def sign_decision(event_id, action):
    raw = f"{event_id}|{action}".encode("utf-8")
    return hmac.new(RELAY_TOKEN.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def valid_decision(event_id, action, signature):
    if not RELAY_TOKEN or not signature:
        return False
    expected = sign_decision(event_id, action)
    return hmac.compare_digest(expected, signature)


def send_telegram(text, reply_markup=None):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("telegram_not_configured")
    fields = {"chat_id": CHAT_ID, "text": text}
    if reply_markup is not None:
        fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    body = urlencode(fields).encode("utf-8")
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


def decision_keyboard(event_id):
    approve_sig = sign_decision(event_id, "approve")
    cancel_sig = sign_decision(event_id, "cancel")
    approve_url = (
        f"{PUBLIC_BASE_URL}/decision?id={quote(event_id, safe='')}"
        f"&action=approve&sig={approve_sig}"
    )
    cancel_url = (
        f"{PUBLIC_BASE_URL}/decision?id={quote(event_id, safe='')}"
        f"&action=cancel&sig={cancel_sig}"
    )
    return {
        "inline_keyboard": [
            [
                {"text": "✅ تنفيذ الصفقة", "url": approve_url},
                {"text": "❌ إلغاء", "url": cancel_url},
            ]
        ]
    }


def event_expired(event):
    return (time.time() - float(event.get("created_ts", 0))) > APPROVAL_TTL_SECONDS


def decision_page(event_id, action, signature):
    title = "تنفيذ الصفقة" if action == "approve" else "إلغاء الصفقة"
    action_text = "جاري إرسال موافقتك للتنفيذ..." if action == "approve" else "جاري إلغاء الصفقة..."
    payload = json.dumps(
        {"event_id": event_id, "action": action, "sig": signature},
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{html.escape(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0b1220;color:#fff;margin:0;display:grid;place-items:center;min-height:100vh}}
.card{{max-width:460px;margin:24px;padding:28px;border-radius:20px;background:#151f32;text-align:center;box-shadow:0 12px 40px #0006}}
h2{{margin-top:0}} .muted{{opacity:.75}} .ok{{color:#63e6be}} .bad{{color:#ff8787}}
</style>
</head>
<body><div class="card"><h2>{html.escape(title)}</h2><p id="status">{html.escape(action_text)}</p><p class="muted">يمكنك إغلاق هذه الصفحة بعد ظهور النتيجة.</p></div>
<script>
(async()=>{{
  const status=document.getElementById("status");
  try {{
    const r=await fetch("/decision",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:{json.dumps(payload)}}});
    const d=await r.json();
    if(d.ok){{
      status.className="ok";
      status.textContent=d.message || "تم.";
    }} else {{
      status.className="bad";
      status.textContent=d.message || d.error || "تعذر تنفيذ الطلب.";
    }}
  }} catch(e) {{
    status.className="bad";
    status.textContent="تعذر الاتصال. ارجع لتيليغرام وحاول من جديد.";
  }}
}})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LaithLiveSignalRelay/2.0"

    def _json(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, code, body):
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        return bool(RELAY_TOKEN) and self.headers.get("X-Relay-Token") == RELAY_TOKEN

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {
                "ok": True,
                "telegram_configured": bool(TOKEN and CHAT_ID),
                "relay_token_configured": bool(RELAY_TOKEN),
                "approval_flow": True,
                "approval_ttl_seconds": APPROVAL_TTL_SECONDS,
            })
            return

        if parsed.path == "/decision":
            q = parse_qs(parsed.query)
            event_id = (q.get("id") or [""])[0]
            action = (q.get("action") or [""])[0]
            signature = (q.get("sig") or [""])[0]
            if action not in ("approve", "cancel") or not valid_decision(event_id, action, signature):
                self._html(403, "<h2>الرابط غير صالح.</h2>")
                return
            self._html(200, decision_page(event_id, action, signature))
            return

        if parsed.path == "/next-approved":
            if not self._authorized():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            now = time.time()
            for event_id, event in list(_events.items()):
                if event.get("status") != "approved":
                    continue
                if event_expired(event):
                    event["status"] = "expired"
                    continue
                lease_until = float(event.get("lease_until") or 0)
                if lease_until > now:
                    continue
                event["lease_until"] = now + LEASE_SECONDS
                self._json(200, {
                    "ok": True,
                    "event": {
                        "event_id": event_id,
                        "signal": event.get("signal") or {},
                        "created_ts": event.get("created_ts"),
                    },
                })
                return
            self._json(200, {"ok": True, "event": None})
            return

        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/signal":
            if not self._authorized():
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

                signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
                executable = signal.get("side") in ("BUY", "SELL") and bool(signal.get("sl")) and bool(signal.get("tp"))
                if executable:
                    _events[event_id] = {
                        "status": "pending",
                        "created_ts": time.time(),
                        "signal": signal,
                    }
                    send_telegram(text, decision_keyboard(event_id))
                else:
                    send_telegram(text)

                self._json(200, {"ok": True, "duplicate": False, "approval_available": executable})
            except Exception as exc:
                self._json(502, {"ok": False, "error": type(exc).__name__})
            return

        if parsed.path == "/decision":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                event_id = str(payload.get("event_id") or "")
                action = str(payload.get("action") or "")
                signature = str(payload.get("sig") or "")
                if action not in ("approve", "cancel") or not valid_decision(event_id, action, signature):
                    self._json(403, {"ok": False, "error": "invalid_signature", "message": "الرابط غير صالح."})
                    return
                event = _events.get(event_id)
                if not event:
                    self._json(404, {"ok": False, "error": "event_not_found", "message": "الصفقة لم تعد متاحة."})
                    return
                if event_expired(event):
                    event["status"] = "expired"
                    self._json(410, {"ok": False, "error": "expired", "message": "انتهت صلاحية الصفقة؛ انتظر إشارة جديدة."})
                    return
                if action == "cancel":
                    if event.get("status") in ("executed", "failed"):
                        self._json(409, {"ok": False, "error": "already_final", "message": "تمت معالجة الصفقة مسبقاً."})
                        return
                    event["status"] = "cancelled"
                    event["decided_ts"] = time.time()
                    send_telegram("❌ تم إلغاء صفقة الجسر؛ لن يتم إرسال أمر للـ MT5.")
                    self._json(200, {"ok": True, "message": "تم إلغاء الصفقة."})
                    return

                if event.get("status") == "approved":
                    self._json(200, {"ok": True, "message": "الموافقة مسجلة بالفعل؛ جاري انتظار MT5."})
                    return
                if event.get("status") in ("executed", "failed", "cancelled"):
                    self._json(409, {"ok": False, "error": "already_final", "message": "تمت معالجة الصفقة مسبقاً."})
                    return

                event["status"] = "approved"
                event["decided_ts"] = time.time()
                event["lease_until"] = 0
                self._json(200, {"ok": True, "message": "✅ تم تسجيل الموافقة. الصفقة جاهزة لموصل التنفيذ على MT5."})
            except Exception as exc:
                self._json(500, {"ok": False, "error": type(exc).__name__})
            return

        if parsed.path == "/result":
            if not self._authorized():
                self._json(401, {"ok": False, "error": "unauthorized"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                event_id = str(payload.get("event_id") or "")
                event = _events.get(event_id)
                if not event:
                    self._json(404, {"ok": False, "error": "event_not_found"})
                    return
                ok = bool(payload.get("ok"))
                event["status"] = "executed" if ok else "failed"
                event["result"] = payload
                if ok:
                    ticket = payload.get("ticket") or "-"
                    price = payload.get("price")
                    side = (event.get("signal") or {}).get("side", "-")
                    send_telegram(
                        f"✅ تم تنفيذ صفقة الجسر على الحساب الحقيقي\n"
                        f"الاتجاه: {side}\n"
                        f"السعر: {price if price is not None else '-'}\n"
                        f"التذكرة: {ticket}"
                    )
                else:
                    reason = str(payload.get("reason") or "unknown")
                    send_telegram(f"⛔ لم تُنفذ صفقة الجسر على الحساب الحقيقي\nالسبب: {reason}")
                self._json(200, {"ok": True})
            except Exception as exc:
                self._json(500, {"ok": False, "error": type(exc).__name__})
            return

        self._json(404, {"ok": False, "error": "not_found"})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    if not TOKEN or not CHAT_ID or not RELAY_TOKEN:
        raise SystemExit("missing required relay configuration")
    print(f"live-signal-relay v2 listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
