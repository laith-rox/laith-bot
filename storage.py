"""SQLite state and transactional outbox on a persistent, single-writer volume."""
import json
from pathlib import Path
import sqlite3


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY, created REAL NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_open_signal ON signals((1))
                WHERE status IN ('pending', 'active', 'uncertain_delivery');
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, signal_id TEXT,
                message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                created REAL NOT NULL, expires REAL, next_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, message_id INTEGER,
                last_attempt REAL, error TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id));
            CREATE TABLE IF NOT EXISTS decisions (
                time REAL PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS bars (
                time REAL PRIMARY KEY, open REAL, high REAL, low REAL, close REAL);
        """)

    def close(self):
        self.db.close()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, key, value):
        self.db.execute("INSERT INTO kv VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, allow_nan=False)))

    def set(self, key, value):
        with self.db:
            self._set(key, value)

    def _save_trade(self, trade):
        self.db.execute("INSERT INTO signals VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                        "status=excluded.status, data=excluded.data",
                        (trade["id"], trade["created"], trade["status"], json.dumps(trade, allow_nan=False)))

    def trade(self, signal_id):
        row = self.db.execute("SELECT data FROM signals WHERE id=?", (signal_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def active(self):
        row = self.db.execute("SELECT data FROM signals WHERE status IN "
                              "('pending','active','uncertain_delivery') LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def _enqueue(self, event_id, kind, message, now, signal_id=None, expires=None):
        self.db.execute("INSERT OR IGNORE INTO outbox "
                        "(id,kind,signal_id,message,created,expires,next_at) VALUES (?,?,?,?,?,?,?)",
                        (event_id, kind, signal_id, message, now, expires, now))

    def enqueue(self, event_id, kind, message, now, signal_id=None, expires=None):
        with self.db:
            self._enqueue(event_id, kind, message, now, signal_id, expires)

    def prepare_entry(self, trade, message, now):
        with self.db:
            if self.active() or self.trade(trade["id"]):
                return False
            self._save_trade(trade)
            self._enqueue(trade["id"] + ":entry", "entry", message, now, trade["id"], now + 120)
        return True

    def prepare_report(self, report, message, now):
        with self.db:
            if self.get("paused", False):
                return False
            if self.db.execute("SELECT 1 FROM outbox WHERE id=?", (report["id"],)).fetchone():
                return False
            self._set("report_candidate", report)
            self._enqueue(report["id"], "report", message, now, expires=min(now + 120, report["ends_at"]))
        return True

    def prepare_early(self, watch, message, now):
        with self.db:
            if self.active() or self.get("paused", False) or self.get("early_watch"):
                return False
            recent = self.db.execute("SELECT 1 FROM outbox WHERE kind='early' AND created>?",
                                     (now - 3600,)).fetchone()
            if recent:
                return False
            self._set("early_candidate", watch)
            self._enqueue(watch["id"] + ":early", "early", message, now, expires=now + 120)
        return True

    def save_transition(self, trade, messages, now):
        with self.db:
            self._save_trade(trade)
            for kind, message in messages:
                self._enqueue(trade["id"] + ":" + kind, kind, message, now, trade["id"])

    def recover_inflight(self, now):
        # Telegram has no sendMessage idempotency key. A crash after POST may mean delivered.
        for row in self.db.execute("SELECT id FROM outbox WHERE status='inflight'").fetchall():
            self.finish(row["id"], "uncertain", now, error="restart_during_send")

    def claim(self, now):
        with self.db:
            expired = self.db.execute("SELECT * FROM outbox WHERE status='pending' "
                                      "AND expires IS NOT NULL AND expires<=?", (now,)).fetchall()
            for row in expired:
                self.db.execute("UPDATE outbox SET status='expired' WHERE id=?", (row["id"],))
                if row["kind"] == "entry":
                    trade = self.trade(row["signal_id"])
                    if trade["status"] == "pending":
                        trade["status"] = "undelivered"
                        self._save_trade(trade)
            row = self.db.execute("SELECT * FROM outbox WHERE status='pending' AND next_at<=? "
                                  "ORDER BY CASE WHEN kind='emergency' THEN 0 ELSE 1 END, created,id LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE outbox SET status='inflight', attempts=attempts+1, last_attempt=? "
                            "WHERE id=?", (now, row["id"]))
            return dict(self.db.execute("SELECT * FROM outbox WHERE id=?", (row["id"],)).fetchone())

    def finish(self, event_id, status, now, message_id=None, error=None, retry_after=0):
        if status not in ("sent", "retry", "failed", "uncertain"):
            raise ValueError("invalid_delivery_status")
        with self.db:
            row = self.db.execute("SELECT * FROM outbox WHERE id=?", (event_id,)).fetchone()
            if row is None or row["status"] != "inflight":
                raise ValueError("delivery_not_claimed")
            final = "pending" if status == "retry" and row["attempts"] < 5 else (
                "failed" if status == "retry" else status)
            delay = max(retry_after, min(300, 5 * 2 ** (row["attempts"] - 1)))
            self.db.execute("UPDATE outbox SET status=?, message_id=?, error=?, next_at=? WHERE id=?",
                            (final, message_id, error, now + delay, event_id))
            if row["kind"] == "report" and final in ("sent", "uncertain"):
                report = self.get("report_candidate")
                if report and report["id"] == row["id"]:
                    report["delivery_uncertain"] = final == "uncertain"
                    if report.get("watch"):
                        report["watch"].update(status="active" if final == "sent" else "uncertain_delivery",
                                               announced=now, delivery_uncertain=final == "uncertain")
                    self._set("current_report", report)
            if row["kind"] == "early" and final in ("sent", "uncertain"):
                watch = self.get("early_candidate")
                if watch and row["id"] == watch["id"] + ":early":
                    watch.update(status="active" if final == "sent" else "uncertain_delivery",
                                 announced=now, delivery_uncertain=final == "uncertain")
                    self._set("early_watch", watch)
            if row["kind"] == "entry":
                trade = self.trade(row["signal_id"])
                if final == "sent":
                    trade.update(status="active", announced=now, message_id=message_id)
                    self._set("last_signal_at", now)
                    self._set("early_watch", None)
                elif final == "uncertain":
                    trade.update(status="uncertain_delivery", announced=now, delivery_uncertain=True)
                    self._set("paused", True)
                    self._set("pause_reason", "delivery_uncertain")
                elif final == "failed":
                    trade["status"] = "undelivered"
                self._save_trade(trade)

    def pause(self, paused, reason="user"):
        with self.db:
            self._set("paused", paused)
            self._set("pause_reason", reason if paused else None)
            if paused:
                self.db.execute("UPDATE outbox SET status='expired' WHERE kind IN ('early','report') AND status='pending'")
                active = self.active()
                if active and active["status"] == "pending":
                    active["status"] = "undelivered"
                    self._save_trade(active)
                    self.db.execute("UPDATE outbox SET status='expired' WHERE signal_id=? "
                                    "AND kind='entry' AND status='pending'", (active["id"],))

    def record(self, now, decision, bars):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO decisions VALUES (?,?)",
                            (now.timestamp(), json.dumps(decision, allow_nan=False)))
            self.db.executemany("INSERT OR IGNORE INTO bars VALUES (?,?,?,?,?)",
                                [(b.start.timestamp(), b.open, b.high, b.low, b.close) for b in bars])
            self._set("last_analysis", decision)
            self._set("last_market_ok", now.timestamp())
            self.db.execute("DELETE FROM decisions WHERE time<?", (now.timestamp() - 90*86400,))
            self.db.execute("DELETE FROM bars WHERE time<?", (now.timestamp() - 180*86400,))

    def completed(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT data FROM signals WHERE status='closed' ORDER BY created")]

    def stats(self):
        all_closed = self.completed()
        valid = [t for t in all_closed if t.get("r") is not None]
        equity = peak = drawdown = 0.0
        for trade in sorted(valid, key=lambda t: t["closed"]):
            equity += trade["r"]
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        return {"closed": len(all_closed), "measured": len(valid),
                "unresolved": len(all_closed) - len(valid),
                "wins": sum(t["r"] > 0 for t in valid), "losses": sum(t["r"] < 0 for t in valid),
                "flat": sum(t["r"] == 0 for t in valid), "total_r": equity, "drawdown_r": drawdown}
