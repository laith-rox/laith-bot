"""Laith Gold Signals v2: persistent monitoring and Telegram alerts only."""
import argparse
import csv
from datetime import datetime, time as wall_time, timezone
import fcntl
from html import escape
import logging
import os
from pathlib import Path
import signal
import sys
import time

from engine import analyze, make_trade, advance_trade
from market import Market, DataError
from messages import entry, transition, stats, status, local_time, LOCAL, REASONS
from news import NewsGuard
from storage import Store
from transport import Telegram, SecretFilter, dispatch

VERSION = "2.0.0"
UTC = timezone.utc
LOG = logging.getLogger("laith")


def entry_window(now):
    local = now.astimezone(LOCAL)
    return local.weekday() < 5 and wall_time(4, 30) <= local.time().replace(tzinfo=None) < wall_time(23, 30)


def daily_risk_blocked(store, now, limit=3.0):
    today = now.astimezone(LOCAL).date()
    total = 0.0
    for trade in store.completed():
        if datetime.fromtimestamp(trade["closed"], LOCAL).date() == today:
            # Unmeasurable outcomes cannot evade the daily brake.
            total += trade["r"] if trade.get("r") is not None else -1.0
    return total <= -limit


class App:
    def __init__(self, store, market, telegram, news, cooldown=60):
        self.store, self.market, self.telegram, self.news = store, market, telegram, news
        self.cooldown = cooldown
        self.started = time.time()

    def cycle(self, now):
        epoch = now.timestamp()
        self.store.set("heartbeat", epoch)
        active = self.store.active()
        if not entry_window(now) and not active:
            self.store.set("last_analysis", {"side": "WAIT", "reason": "outside_entry_window"})
            return
        try:
            bars = self.market.fetch(now)
        except DataError as exc:
            reason = str(exc)
            failures = self.store.get("data_failures", 0) + 1
            self.store.set("data_failures", failures)
            self.store.set("last_error", reason)
            LOG.warning("market_unavailable reason=%s consecutive=%s", reason, failures)
            last_alert = self.store.get("last_data_alert", 0)
            if failures >= 3 and epoch - last_alert >= 3600:
                self.store.enqueue("health:" + str(int(epoch // 3600)), "health",
                    "⚠️ تعذّر تحديث أسعار بوت ليث. اقتراحات الدخول متوقفة حتى عودة بيانات سليمة. "
                    "متابعة الوقف عند وسيطك ضرورية خلال الانقطاع.",
                    epoch, expires=epoch + 3600)
                self.store.set("last_data_alert", epoch)
            return

        # Position monitoring always precedes entry filters, including pause and news.
        if active and active["status"] != "pending":
            updated, events = advance_trade(active, bars)
            self.store.save_transition(updated,
                [(event["kind"], transition(updated, event["kind"])) for event in events], epoch)

        if self.store.get("data_failures", 0) >= 3:
            self.store.enqueue("recovery:" + str(int(epoch)), "health",
                "✅ عادت بيانات أسعار بوت ليث. يُستأنف التحليل وفق شروط الدخول والحماية.", epoch,
                expires=epoch + 3600)
        self.store.set("data_failures", 0)
        self.store.set("last_error", None)
        try:
            decision = analyze(bars, now)
        except DataError as exc:
            decision = {"side": "WAIT", "reason": str(exc)}
        allowed_news, news_reason, events = self.news.check(now)
        for event in events:
            if event["time"] >= epoch:
                self.store.enqueue("news:" + event["id"], "news",
                    "🗓️ <b>حماية حول خبر أمريكي عالي التأثير</b>\n" +
                    escape(event["title"]) + "\n" + local_time(event["time"]) +
                    " فلسطين.\nإيقاف إشارات الدخول 30 دقيقة قبله و15 دقيقة بعده؛ "
                    "متابعة الإشارة الموجودة تستمر. التصنيف لا يتنبأ باتجاه السعر.",
                    epoch, expires=event["time"] + 900)

        original_side = decision["side"]
        active = self.store.active()
        if self.store.get("paused", False):
            reason = "paused"
        elif active:
            reason = "active_signal"
        elif not entry_window(now):
            reason = "outside_entry_window"
        elif not allowed_news:
            reason = news_reason
        elif daily_risk_blocked(self.store, now):
            reason = "daily_risk_limit"
        elif epoch - self.store.get("last_signal_at", 0) < self.cooldown * 60:
            reason = "cooldown"
        elif decision.get("bar") and self.store.get("evaluated_bar") == decision["bar"]:
            reason = "already_evaluated"
        else:
            reason = None

        if decision.get("bar"):
            self.store.set("evaluated_bar", decision["bar"])
        if reason:
            decision = dict(decision, model_side=original_side, side="WAIT", reason=reason)
        self.store.record(now, decision, bars)
        LOG.info("analysis side=%s reason=%s buy=%s sell=%s closed_5m=%s last_close=%s",
                 decision["side"], decision["reason"], decision.get("buy"), decision.get("sell"),
                 len(bars), bars[-1].end.isoformat())

        if active and active["status"] != "pending" and epoch - self.store.get("last_hourly", 0) >= 3600:
            self.store.enqueue("hourly:" + active["id"] + ":" + str(int(epoch // 3600)), "review",
                "🔎 <b>مراجعة إشارة ليث</b> <code>" + active["id"] + "</code>\n"
                + ("اتجاه النموذج الحالي يوافق الإشارة." if original_side == active["side"]
                   else "شروط الدخول الحالية لا تؤكد اتجاه الإشارة؛ راقب وقفك.")
                + "\nهذه مراجعة لنفس النموذج، وتستمر متابعة المستويات كل 5د.",
                epoch, signal_id=active["id"], expires=epoch + 3600)
            self.store.set("last_hourly", epoch)
        if decision["side"] in ("BUY", "SELL"):
            trade = make_trade(decision, now)
            if self.store.prepare_entry(trade, entry(trade, decision), epoch):
                LOG.info("signal_prepared id=%s side=%s", trade["id"], trade["side"])
        if reason == "daily_risk_limit":
            self.store.enqueue("risk:" + str(now.astimezone(LOCAL).date()), "risk",
                "⏸️ بلغ نموذج الإشارات حد الخسارة اليومي 3R. "
                "تتوقف اقتراحات الدخول لبقية اليوم بتوقيت فلسطين. "
                "هذا الحد يخص سجل البوت الافتراضي، وليس حساب الوسيط.", epoch, expires=epoch + 86400)

    def commands(self, now):
        offset = self.store.get("update_offset", 0)
        updates = self.telegram.read("getUpdates", offset=offset, timeout=0,
                                     allowed_updates='["message"]', limit=20)
        if not isinstance(updates, list):
            raise RuntimeError("telegram_updates_invalid")
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                continue
            message = update.get("message", {})
            chat = message.get("chat", {})
            sender = message.get("from", {})
            authorized = (chat.get("type") == "private"
                          and str(chat.get("id")) == self.telegram.chat_id
                          and str(sender.get("id")) == self.telegram.chat_id)
            recent = now.timestamp() - 300 <= message.get("date", 0) <= now.timestamp() + 30
            words = message.get("text", "").split()
            command = words[0].split("@")[0].lower() if words else ""
            text = None
            if authorized and recent:
                if command in ("/start", "/help"):
                    text = ("🥇 بوت ليث لإشارات الذهب ومتابعتها.\n"
                            "/status حالة البوت والإشارة\n/stats سجل النتائج\n"
                            "/pause إيقاف إشارات دخول جديدة مع استمرار متابعة الحالية\n"
                            "/resume استئناف الدخول عند اجتياز شروط البيانات والأخبار والمخاطر")
                elif command == "/status":
                    text = status(self.store)
                elif command == "/stats":
                    text = stats(self.store)
                elif command in ("/pause", "/resume"):
                    self.store.pause(command == "/pause")
                    text = ("⏸️ توقفت إشارات الدخول الجديدة. متابعة الإشارة الحالية مستمرة."
                            if command == "/pause" else
                            "▶️ استُؤنفت مراقبة فرص الدخول. شروط البيانات والأخبار وحد المخاطر ما زالت مطبّقة.")
            if text:
                self.store.enqueue("command:" + str(update_id), "command", text, now.timestamp(),
                                   expires=now.timestamp() + 300)
            self.store.set("update_offset", max(offset, update_id + 1))
            offset = max(offset, update_id + 1)


def configure_logging(token, key):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(SecretFilter((token, key)))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Read-only market preview; never sends Telegram")
    parser.add_argument("--stats", action="store_true", help="Print local signal statistics")
    parser.add_argument("--export-csv", metavar="PATH", help="Export stored closed five-minute candles")
    args = parser.parse_args()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
    configure_logging(token, key)
    if os.getenv("SYMBOL", "XAU/USD").strip().upper() != "XAU/USD":
        raise RuntimeError("this_bot_requires_XAU_USD")
    mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    state_dir = Path(os.getenv("STATE_DIR", mount or "./data")).resolve()
    if args.once:
        if not key:
            raise RuntimeError("missing_market_key")
        now = datetime.now(UTC)
        print(analyze(Market(key).fetch(now), now))
        return
    if os.getenv("RAILWAY_ENVIRONMENT_ID"):
        if not mount or not state_dir.is_relative_to(Path(mount).resolve()):
            raise RuntimeError("persistent_volume_required")
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = open(state_dir / "worker.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("another_worker_owns_state") from None
    store = Store(state_dir / "laith.sqlite3")
    try:
        if args.stats:
            print(stats(store))
            return
        if args.export_csv:
            with open(args.export_csv, "w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["datetime", "open", "high", "low", "close"])
                for row in store.db.execute("SELECT * FROM bars ORDER BY time"):
                    writer.writerow([datetime.fromtimestamp(row["time"], UTC).isoformat(),
                                     row["open"], row["high"], row["low"], row["close"]])
            return
        if not (token and chat_id and key):
            raise RuntimeError("missing_required_environment_variables")
        telegram = Telegram(token, chat_id)
        commands_enabled = telegram.verify(os.getenv("EXPECTED_BOT_USERNAME", "LaithGoldSignalsBot"))
        store.recover_inflight(time.time())
        app = App(store, Market(key), telegram, NewsGuard(store),
                  cooldown=max(60, int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "60"))))
        interval = max(300, int(os.getenv("CHECK_INTERVAL_SECONDS", "300")))
        LOG.info("laith_bot_started version=%s persistent_state=%s commands=%s interval=%s",
                 VERSION, bool(mount), commands_enabled, interval)
        store.enqueue("release:" + VERSION, "service",
            "✅ <b>تم تحديث بوت ليث</b>\nشموع مغلقة، حفظ دائم، متابعة أهداف ووقف، "
            "وحماية حول الأخبار. /status للحالة و/stats للنتائج.\n"
            "تبدأ المتابعة والسجلات بالإشارات الجديدة بعد التحديث.\n"
            "المتابعة تحليلية كل 5د؛ البوت لا ينفّذ أوامر عند الوسيط.", time.time())
        running = True

        def stop(*_):
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        next_market = next_commands = 0.0
        while running:
            now = datetime.now(UTC)
            if commands_enabled and now.timestamp() >= next_commands:
                try:
                    app.commands(now)
                except RuntimeError:
                    LOG.warning("telegram_command_poll_unavailable")
                next_commands = time.time() + 15
            if now.timestamp() >= next_market:
                app.cycle(now)
                next_market = (int(time.time()) // interval + 1) * interval + 15
            dispatch(store, telegram)
            time.sleep(2)
    finally:
        store.close()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never stringify unexpected exceptions: requests errors may include secret URLs.
        known = {"persistent_volume_required", "another_worker_owns_state", "missing_market_key",
                 "this_bot_requires_XAU_USD", "missing_required_environment_variables",
                 "telegram_bot_identity_mismatch", "telegram_read_rejected", "telegram_read_failed"}
        safe = str(exc) if isinstance(exc, DataError) or str(exc) in known else type(exc).__name__
        LOG.error("fatal_stopped reason=%s", safe)
        sys.exit(1)
