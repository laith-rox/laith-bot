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
from alerts import reversal
from reports import snapshot, report_message, follow_message
from market import Market, DataError, require_fresh
from messages import entry, transition, stats, status, local_time, LOCAL, REASONS, early, emergency
from news import NewsGuard
from storage import Store
from transport import Telegram, SecretFilter, dispatch
from fast_service import start_worker, fast_status
from timing import DecisionClock, decision_metadata

VERSION = "2.6.0"
UTC = timezone.utc
LOG = logging.getLogger("laith")


def entry_window(now):
    local = now.astimezone(LOCAL)
    # Main signal engine may prepare entries throughout the trading day, Monday-Friday.
    # Market-data freshness, news, risk, cooldown, and active-signal gates still apply.
    return local.weekday() < 5


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

    def monitor_reversal(self, watch, decision, epoch, is_early=False):
        key = "reversal:" + watch["id"]
        level, state = reversal(watch, decision, self.store.get(key))
        self.store.set(key, state)
        if level:
            self.store.enqueue(key + ":" + level, "emergency",
                emergency(watch, decision, level, is_early), epoch,
                signal_id=None if is_early else watch["id"], expires=epoch + 300)
            LOG.info("reversal_detected id=%s level=%s early=%s", watch["id"], level, is_early)

    def monitor_early(self, bars, decision, now):
        watch = self.store.get("early_watch")
        if not watch:
            return
        epoch = now.timestamp()
        updated, events = advance_trade(watch, bars)
        for event in events:
            self.store.enqueue(watch["id"] + ":early:" + event["kind"], "review",
                "🟠 <b>متابعة السيناريو المبكّر</b> <code>" + watch["id"] + "</code>\n" +
                ("رُصد الهدف الأول؛ يقترح النموذج حماية عند المرجع الأصلي."
                 if event["kind"] == "tp1" else
                 "انتهت المتابعة: " + {"TP2": "رُصد الهدف الثاني", "STOP": "رُصد مستوى الإلغاء",
                 "PROTECTED_STOP": "رُصد مستوى الحماية", "AMBIGUOUS": "لمسات مستويات غير محسومة"}[updated["outcome"]]) +
                "\nهذه متابعة افتراضية خارج إحصاءات الصفقات؛ البوت لا ينفّذ عند الوسيط.", epoch,
                expires=epoch + 3600)
        if updated["status"] == "closed" or epoch - watch["announced"] >= 14400:
            if updated["status"] != "closed":
                self.store.enqueue(watch["id"] + ":early:expired", "review",
                    "🟠 انتهت متابعة السيناريو المبكّر <code>" + watch["id"] +
                    "</code> بعد 4 ساعات. راجع أي صفقة نفّذتها عند وسيطك.", epoch, expires=epoch + 3600)
            self.store.set("early_watch", None)
        else:
            self.store.set("early_watch", updated)
            self.monitor_reversal(updated, decision, epoch, is_early=True)

    def periodic_reports(self, decision, bars, now, blocked=None):
        epoch = now.timestamp()
        current = self.store.get("current_report")
        if current and current.get("watch") and epoch <= current["ends_at"] + 120:
            watch, _ = advance_trade(current["watch"], bars)
            current["watch"] = watch
            self.store.set("current_report", current)
            self.monitor_reversal(watch, decision, epoch, is_early=True)
        slot = int(epoch // 900)
        eligible = entry_window(now) and not self.store.get("paused", False)
        if eligible and not self.store.db.execute("SELECT 1 FROM outbox WHERE id=?", ("report-" + str(slot),)).fetchone():
            report = snapshot(decision, now, blocked)
            if self.store.prepare_report(report, report_message(report, decision, current), epoch):
                LOG.info("report_prepared id=%s side=%s qualified=%s", report["id"], report["side"], report["qualified"])
            return
        if current and current["slot"] == slot and int(epoch // 300) > int(current["created"] // 300):
            self.store.enqueue(current["id"] + ":follow:" + str(int(epoch // 300)), "follow",
                follow_message(current, decision, blocked), epoch,
                expires=min(epoch + 120, current["ends_at"]))

    def cycle(self, now, clock=None):
        clock = clock or DecisionClock(now)
        epoch = now.timestamp()
        self.store.set("heartbeat", epoch)
        active = self.store.active()
        if not entry_window(now) and not active and not self.store.get("early_watch"):
            self.store.set("last_analysis", {"side": "WAIT", "reason": "outside_entry_window"})
            return
        try:
            bars = self.market.fetch(now)
        except DataError as exc:
            now = clock.now()
            epoch = now.timestamp()
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
            self.periodic_reports({"side": "WAIT", "reason": reason}, [], now, reason)
            return

        now = clock.now()
        epoch = now.timestamp()
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
            now = clock.now()
            epoch = now.timestamp()
            require_fresh(bars,now,120)
        except DataError as exc:
            decision = {"side": "WAIT", "reason": str(exc)}
        # Exit warnings run before entry/news/pause gates and use only fresh analysis.
        active = self.store.active()
        if active and active["status"] != "pending":
            self.monitor_reversal(active, decision, epoch)
        self.monitor_early(bars, decision, now)
        allowed_news, news_reason, events = self.news.check(now)
        now = clock.now()
        epoch = now.timestamp()
        try:
            require_fresh(bars,now,120)
            decision = dict(decision, **decision_metadata(bars,now))
        except DataError as exc:
            decision = {"side":"WAIT", "reason":str(exc)}
        for event in events:
            if event["time"] >= epoch:
                self.store.enqueue("news:" + event["id"], "news",
                    "🗓️ <b>حماية حول خبر أمريكي عالي التأثير</b>\n" +
                    escape(event["title"]) + "\n" + local_time(event["time"]) +
                    " فلسطين.\nإيقاف إشارات الدخول 30 دقيقة قبله و15 دقيقة بعده؛ "
                    "متابعة الإشارة الموجودة تستمر. التصنيف لا يتنبأ باتجاه السعر.",
                    epoch, expires=event["time"] + 900)

        raw_decision = dict(decision)
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

        report_block = reason if reason not in (None, "already_evaluated") else None
        self.periodic_reports(raw_decision, bars, now, report_block)
        if decision.get("bar"):
            self.store.set("evaluated_bar", decision["bar"])
        if reason:
            decision = dict(decision, model_side=original_side, side="WAIT", reason=reason)
        self.store.record(now, decision, bars)
        LOG.info("analysis side=%s reason=%s buy=%s sell=%s closed_5m=%s last_close=%s",
                 decision["side"], decision["reason"], decision.get("buy"), decision.get("sell"),
                 len(bars), bars[-1].end.isoformat())
        if raw_decision.get("context"):
            context = raw_decision["context"]
            LOG.info("market_context price=%.2f trend=%s structure=%s phase=%s support=%.2f resistance=%.2f",
                     raw_decision["price"], context["trend"], context["local_structure"],
                     context["phase"], context["support"], context["resistance"])

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
                            "/status حالة البوت والإشارة\n/stats سجل النتائج\n/fast فحص المسار السريع التجريبي\n"
                            "/pause إيقاف إشارات دخول جديدة مع استمرار متابعة الحالية\n"
                            "/resume استئناف الدخول عند اجتياز شروط البيانات والأخبار والمخاطر")
                elif command == "/status":
                    text = status(self.store)
                elif command == "/fast":
                    text = fast_status(self.store)
                elif command == "/stats":
                    text = stats(self.store)
                elif command == "/pause":
                    self.store.set("paused", True)
                    text = "⏸️ تم إيقاف إشارات الدخول الجديدة. متابعة الإشارة الحالية والحماية مستمرة."
                elif command == "/resume":
                    self.store.set("paused", False)
                    text = "▶️ تم استئناف إشارات الدخول الجديدة وفق شروط البيانات والأخبار والمخاطر."
            if text:
                self.store.enqueue("command:" + str(update_id), "command", text, now.timestamp(), expires=now.timestamp()+300)
            self.store.set("update_offset", update_id + 1)


def run(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for secret in (args.telegram_token, args.twelve_key, args.telegram_chat):
        if secret:
            logging.getLogger().addFilter(SecretFilter(secret))
    store = Store(args.db)
    telegram = Telegram(args.telegram_token, args.telegram_chat)
    market = Market(args.twelve_key)
    news = NewsGuard(store)
    stop = start_worker(args.db,args.twelve_key)
    try:
        LOG.info("starting version=%s",VERSION)
        while True:
            now = datetime.now(UTC)
            try:
                app = App(store,market,telegram,news,args.cooldown)
                app.commands(now)
                app.cycle(now)
                dispatch(store,telegram,now.timestamp())
            except Exception as exc:
                LOG.exception("cycle_failed category=%s",type(exc).__name__)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        store.close()


def parser():
    p=argparse.ArgumentParser()
    p.add_argument('--db',default=os.getenv('DB_PATH','/data/laith.db'))
    p.add_argument('--telegram-token',default=os.getenv('TELEGRAM_BOT_TOKEN'))
    p.add_argument('--telegram-chat',default=os.getenv('TELEGRAM_CHAT_ID'))
    p.add_argument('--twelve-key',default=os.getenv('TWELVE_DATA_API_KEY'))
    p.add_argument('--interval',type=int,default=int(os.getenv('CHECK_INTERVAL_SECONDS','20')))
    p.add_argument('--cooldown',type=int,default=int(os.getenv('SIGNAL_COOLDOWN_MINUTES','60')))
    return p


if __name__ == '__main__':
    run(parser().parse_args())
