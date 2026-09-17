"""Fail-closed HTTP bridge between Laith V4 paper signals and an MT5 executor.

The bridge is intentionally separate from the analysis engine. It publishes only
fresh official V4 paper entries, deduplicates by signal id, and defaults to demo
mode. Live mode requires an explicit server-side arming value and the MT5 EA has
its own live-trading switch as a second gate.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import os
import sqlite3
import threading
import time
from urllib.parse import urlparse

LOG = logging.getLogger("laith.v4.mt5")


def _truthy(name, default="0"):
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def bridge_enabled():
    return _truthy("V4_MT5_BRIDGE_ENABLED", "0")


def bridge_mode():
    mode = str(os.getenv("V4_MT5_EXECUTION_MODE", "demo")).strip().lower()
    if mode not in {"demo", "live"}:
        return "disabled"
    if mode == "live" and os.getenv("V4_MT5_LIVE_ARMED") != "YES_I_UNDERSTAND":
        return "disabled"
    return mode


def _ensure_schema_conn(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS v4_exec_orders(
            id TEXT PRIMARY KEY,
            created REAL NOT NULL,
            expires REAL NOT NULL,
            status TEXT NOT NULL,
            data TEXT NOT NULL,
            ack TEXT,
            ack_at REAL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS v4_exec_status_idx ON v4_exec_orders(status, created)")
    db.commit()


def ensure_schema(store):
    _ensure_schema_conn(store.db)


def _float(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("invalid_" + name)
    if not (result == result and abs(result) != float("inf")):
        raise ValueError("invalid_" + name)
    return result


def publish_official_order(store, trade, now=None):
    """Persist one fresh official V4 order for the MT5 executor, or return None."""
    if not bridge_enabled():
        return None
    mode = bridge_mode()
    if mode == "disabled":
        LOG.error("execution_bridge_blocked reason=mode_not_armed")
        return None
    if not isinstance(trade, dict) or trade.get("generation") != "V4" or not trade.get("paper_only"):
        return None
    if trade.get("status") != "active" or trade.get("side") not in {"BUY", "SELL"}:
        return None

    now = time.time() if now is None else float(now)
    announced = _float(trade.get("announced", trade.get("created", now)), "announced")
    max_age = max(15.0, float(os.getenv("V4_MT5_MAX_SIGNAL_AGE_SECONDS", "120")))
    if now - announced > max_age or announced - now > 30:
        return None

    side = trade["side"]
    entry = _float(trade.get("entry"), "entry")
    stop = _float(trade.get("stop"), "stop")
    target = _float(trade.get("tp1"), "tp1")
    if side == "BUY" and not (stop < entry < target):
        LOG.error("execution_bridge_blocked reason=invalid_buy_levels id=%s", trade.get("id"))
        return None
    if side == "SELL" and not (target < entry < stop):
        LOG.error("execution_bridge_blocked reason=invalid_sell_levels id=%s", trade.get("id"))
        return None

    configured_lot = max(0.01, float(os.getenv("V4_MT5_DEMO_LOT", "0.01")))
    max_lot = max(0.01, float(os.getenv("V4_MT5_MAX_LOT", "0.02")))
    lot = min(configured_lot, max_lot)
    signal_id = str(trade.get("id") or "").strip()
    if not signal_id:
        return None
    order_id = "official:" + signal_id
    expires = announced + max_age
    order = {
        "id": order_id,
        "signal_id": signal_id,
        "generation": "V4",
        "stream": "official",
        "mode": mode,
        "symbol": "XAUUSD",
        "side": side,
        "entry": round(entry, 5),
        "stop": round(stop, 5),
        "target": round(target, 5),
        "lot": round(lot, 2),
        "created": announced,
        "expires": expires,
    }
    ensure_schema(store)
    payload = json.dumps(order, separators=(",", ":"), allow_nan=False)
    with store.db:
        store.db.execute(
            "INSERT OR IGNORE INTO v4_exec_orders(id,created,expires,status,data) VALUES (?,?,?,?,?)",
            (order_id, announced, expires, "pending", payload),
        )
    store.set("v4_mt5_last_order", order)
    LOG.info(
        "execution_order_ready id=%s mode=%s side=%s entry=%.2f stop=%.2f target=%.2f lot=%.2f",
        order_id, mode, side, entry, stop, target, lot,
    )
    return order


def _connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    _ensure_schema_conn(db)
    return db


def _safe_field(value):
    return str(value).replace("|", "/").replace("\r", " ").replace("\n", " ")


def _order_line(order):
    fields = [
        "ORDER",
        order["id"],
        order["mode"],
        order["side"],
        order["symbol"],
        order["entry"],
        order["stop"],
        order["target"],
        order["lot"],
        order["expires"],
    ]
    return "|".join(_safe_field(value) for value in fields) + "\n"


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "LaithV4Bridge/1.0"

    def log_message(self, fmt, *args):
        LOG.info("http " + fmt, *args)

    def _send(self, code, body, content_type="text/plain; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self):
        expected = getattr(self.server, "bridge_token", "")
        supplied = self.headers.get("X-Laith-Token", "")
        return bool(expected) and hmac.compare_digest(expected, supplied)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, json.dumps({"ok": True, "mode": getattr(self.server, "bridge_mode", "disabled")}))
            return
        if path not in {"/v1/order", "/v1/order.txt"}:
            self._send(404, "NOT_FOUND\n")
            return
        if not self._authorized():
            self._send(401, "UNAUTHORIZED\n")
            return
        now = time.time()
        db = _connect(self.server.db_path)
        try:
            with db:
                db.execute(
                    "UPDATE v4_exec_orders SET status='expired', ack_at=? "
                    "WHERE status='pending' AND expires<?",
                    (now, now),
                )
            row = db.execute(
                "SELECT data FROM v4_exec_orders WHERE status='pending' AND expires>=? ORDER BY created LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                self._send(200, "NONE\n")
                return
            order = json.loads(row[0])
            if path.endswith(".txt"):
                self._send(200, _order_line(order))
            else:
                self._send(200, json.dumps(order, separators=(",", ":")), "application/json; charset=utf-8")
        finally:
            db.close()

    def do_POST(self):
        if urlparse(self.path).path != "/v1/ack":
            self._send(404, "NOT_FOUND\n")
            return
        if not self._authorized():
            self._send(401, "UNAUTHORIZED\n")
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 4096)
            body = self.rfile.read(length).decode("utf-8", "replace").strip()
            parts = body.split("|", 3)
            if len(parts) < 2:
                raise ValueError("bad_ack")
            order_id = parts[0].strip()
            state = parts[1].strip().lower()
            ticket = parts[2].strip() if len(parts) > 2 else ""
            message = parts[3].strip() if len(parts) > 3 else ""
            if state not in {"opened", "rejected", "duplicate", "error"}:
                raise ValueError("bad_state")
            ack = {
                "state": state,
                "ticket": ticket,
                "message": message[:500],
                "time": time.time(),
            }
        except Exception:
            self._send(400, "BAD_ACK\n")
            return

        db = _connect(self.server.db_path)
        try:
            with db:
                cur = db.execute(
                    "UPDATE v4_exec_orders SET status=?, ack=?, ack_at=? WHERE id=? AND status='pending'",
                    (state, json.dumps(ack, separators=(",", ":")), ack["time"], order_id),
                )
            self._send(200, "OK\n" if cur.rowcount else "ALREADY_DONE\n")
        finally:
            db.close()


def start_bridge_server(db_path):
    """Start the bridge in a daemon thread. Returns the server or None."""
    if not bridge_enabled():
        LOG.info("execution_bridge_disabled")
        return None
    mode = bridge_mode()
    if mode == "disabled":
        LOG.error("execution_bridge_not_started reason=mode_not_armed")
        return None
    token = str(os.getenv("V4_MT5_BRIDGE_TOKEN", ""))
    if len(token) < 24:
        LOG.error("execution_bridge_not_started reason=missing_or_short_token")
        return None
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), BridgeHandler)
    server.db_path = str(db_path)
    server.bridge_token = token
    server.bridge_mode = mode
    thread = threading.Thread(target=server.serve_forever, name="v4-mt5-bridge", daemon=True)
    thread.start()
    LOG.info("execution_bridge_started mode=%s port=%s", mode, port)
    return server
