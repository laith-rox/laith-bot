"""Laith Gold Signals v2: persistent monitoring and Telegram alerts only."""
import argparse
from datetime import datetime, timezone
import logging
import os
import time

from engine import analyze, make_trade, advance_trade
from alerts import reversal
from reports import snapshot, report_message, follow_message, trade_follow_message
from market import Market, DataError, require_fresh
from messages import entry, transition, stats, status, LOCAL, emergency
from news import NewsGuard
from storage import Store
from transport import Telegram, dispatch
from fast_service import start_worker, fast_status
from timing import DecisionClock, decision_metadata

VERSION = "2.6.4"
UTC = timezone.utc
LOG = logging.getLogger("laith")

def entry_window(now):
    local = now.astimezone(LOCAL)
    minutes = local.hour * 60 + local.minute
    return local.weekday() < 5 and 4 * 60 + 30 <= minutes < 23 * 60 + 50

def daily_risk_blocked(store, now, limit=3.0):
    today=now.astimezone(LOCAL).date(); total=0.0
    for trade in store.completed():
        if datetime.fromtimestamp(trade["closed"],LOCAL).date()==today:
            total += trade["r"] if trade.get("r") is not None else -1.0
    return total <= -limit

class App:
    def __init__(self,store,market,telegram,news,cooldown=60):
        self.store,self.market,self.telegram,self.news=store,market,telegram,news; self.cooldown=cooldown

    def monitor_reversal(self,watch,decision,epoch,is_early=False):
        key="reversal:"+watch["id"]; level,state=reversal(watch,decision,self.store.get(key)); self.store.set(key,state)
        if level:
            self.store.enqueue(key+":"+level,"emergency",emergency(watch,decision,level,is_early),epoch,signal_id=None if is_early else watch["id"],expires=epoch+300)

    def monitor_early(self,bars,decision,now):
        watch=self.store.get("early_watch")
        if not watch: return
        epoch=now.timestamp(); updated,events=advance_trade(watch,bars)
        for event in events:
            message = "🟠 <b>تحديث السيناريو المبكّر</b>\n" + transition(updated,event["kind"])
            self.store.enqueue(watch["id"]+":early:"+event["kind"],"review",message,epoch,expires=epoch+3600)
        if updated["status"]=="closed" or epoch-watch["announced"]>=14400: self.store.set("early_watch",None)
        else:
            self.store.set("early_watch",updated); self.monitor_reversal(updated,decision,epoch,True)

    def periodic_reports(self,decision,bars,now,blocked=None):
        epoch=now.timestamp(); slot=int(epoch//900); current=self.store.get("current_report")
        if self.store.has_important_update(epoch):
            self.store.supersede_routine()
            return
        active=self.store.active()
        if active:
            self.store.supersede_routine(keep_signal=active['id'])
            if active['status']=='pending': return
            follow_id=active['id']+':follow:'+str(int(epoch//300))
            if not self.store.db.execute("SELECT 1 FROM outbox WHERE id=?",(follow_id,)).fetchone():
                self.store.enqueue(follow_id,'follow',trade_follow_message(active,decision,now),epoch,
                                   signal_id=active['id'],expires=epoch+300)
                LOG.info('trade_follow_prepared id=%s side=%s',follow_id,active['side'])
            return
        if current and current.get("watch") and bars and epoch <= current["ends_at"]+120:
            watch,_=advance_trade(current["watch"],bars); current["watch"]=watch; self.store.set("current_report",current)
        eligible=entry_window(now) and not self.store.get("paused",False)
        report_id="report-"+str(slot)
        if eligible and not self.store.db.execute("SELECT 1 FROM outbox WHERE id=?",(report_id,)).fetchone():
            report=snapshot(decision,now,blocked)
            if self.store.prepare_report(report,report_message(report,decision,current),epoch): LOG.info("report_prepared id=%s",report["id"])
            return
        current=self.store.get("current_report")
        if current and current["slot"]==slot:
            five_slot=int(epoch//300)
            follow_id=current["id"]+":follow:"+str(five_slot)
            if five_slot > int(current["created"]//300) and not self.store.db.execute("SELECT 1 FROM outbox WHERE id=?",(follow_id,)).fetchone():
                self.store.enqueue(follow_id,"follow",follow_message(current,decision,blocked),epoch,expires=epoch+300)
                LOG.info("follow_prepared id=%s buy=%s sell=%s",follow_id,decision.get("buy"),decision.get("sell"))

    def cycle(self,now,clock=None):
        clock=clock or DecisionClock(now); epoch=now.timestamp(); self.store.set("heartbeat",epoch); active=self.store.active()
        if not entry_window(now) and not active and not self.store.get("early_watch"):
            self.store.set("last_analysis",{"side":"WAIT","reason":"outside_entry_window"}); return
        try: bars=self.market.fetch(now)
        except DataError as exc:
            reason=str(exc); self.store.set("last_error",reason); self.periodic_reports({"side":"WAIT","reason":reason},[],clock.now(),reason); return
        now=clock.now(); epoch=now.timestamp()
        if active and active["status"]!="pending":
            updated,events=advance_trade(active,bars); self.store.save_transition(updated,[(e["kind"],transition(updated,e["kind"])) for e in events],epoch)
        self.store.set("last_error",None)
        try:
            decision=analyze(bars,now); now=clock.now(); epoch=now.timestamp(); require_fresh(bars,now,600); decision=dict(decision,**decision_metadata(bars,now))
        except DataError as exc: decision={"side":"WAIT","reason":str(exc)}
        active=self.store.active()
        if active and active["status"]!="pending": self.monitor_reversal(active,decision,epoch)
        self.monitor_early(bars,decision,now)
        allowed_news,news_reason,_=self.news.check(now)
        now=clock.now(); epoch=now.timestamp()
        try:
            require_fresh(bars,now,600)
        except DataError as exc:
            decision={"side":"WAIT","reason":str(exc)}
        raw_decision=dict(decision); original_side=decision["side"]; active=self.store.active()
        if self.store.get("paused",False): reason="paused"
        elif active: reason="active_signal"
        elif not entry_window(now): reason="outside_entry_window"
        elif not allowed_news: reason=news_reason
        elif daily_risk_blocked(self.store,now): reason="daily_risk_limit"
        elif epoch-self.store.get("last_signal_at",0)<self.cooldown*60: reason="cooldown"
        elif decision.get("bar") and self.store.get("evaluated_bar")==decision["bar"]: reason="already_evaluated"
        else: reason=None
        if decision.get("bar"): self.store.set("evaluated_bar",decision["bar"])
        if reason: decision=dict(decision,model_side=original_side,side="WAIT",reason=reason)
        self.store.record(now,decision,bars)
        LOG.info("analysis side=%s reason=%s buy=%s sell=%s closed_5m=%s last_close=%s",decision["side"],decision.get("reason"),raw_decision.get("buy"),raw_decision.get("sell"),len(bars),bars[-1].end.isoformat())
        if decision["side"] in ("BUY","SELL"):
            try:
                require_fresh(bars,clock.now(),120)
                quote=self.market.quote(clock.now)
                now=clock.now(); epoch=now.timestamp()
                require_fresh(bars,now,120)
                if not entry_window(now): raise DataError('outside_entry_window')
                tolerance=min(1.0,decision['atr']*0.25)
                shift=quote['price']-decision['price']
                if abs(shift)>tolerance: raise DataError('market_price_moved')
                decision=dict(decision)
                for field in ('price','sl','tp1','tp2'): decision[field]+=shift
                trade=make_trade(decision,now)
                trade.update(entry_buy=decision.get('buy'),entry_sell=decision.get('sell'),
                             quote_time=quote['time'],quote_source=quote['source'],
                             price_tolerance=tolerance,
                             entry_expires=min(quote['time']+90,bars[-1].end.timestamp()+120))
                self.store.prepare_entry(trade,entry(trade,decision),epoch)
                LOG.info('entry_quote_verified id=%s price=%.2f source_age=%.1f',
                         trade['id'],trade['entry'],epoch-quote['time'])
            except DataError as exc:
                reason=str(exc); self.store.set('last_error',reason)
                LOG.warning('entry_blocked reason=%s',reason)
        self.periodic_reports(raw_decision,bars,now,reason if reason not in (None,"already_evaluated") else None)

    def commands(self,now):
        offset=self.store.get("update_offset",0); updates=self.telegram.read("getUpdates",offset=offset,timeout=0,allowed_updates='["message"]',limit=20)
        if not isinstance(updates,list): return
        for update in updates:
            uid=update.get("update_id"); message=update.get("message",{}); chat=message.get("chat",{}); sender=message.get("from",{})
            authorized=chat.get("type")=="private" and str(chat.get("id"))==self.telegram.chat_id and str(sender.get("id"))==self.telegram.chat_id
            words=message.get("text","").split(); command=words[0].split("@")[0].lower() if words else ""; text=None
            if authorized:
                if command in ("/start","/help"): text="🥇 بوت ليث لإشارات الذهب ومتابعتها.\n/status حالة البوت\n/pause إيقاف الدخول\n/resume استئناف الدخول"
                elif command=="/status": text=status(self.store)
                elif command=="/stats": text=stats(self.store)
                elif command=="/fast": text=fast_status(self.store)
                elif command=="/pause": self.store.set("paused",True); text="⏸️ تم إيقاف إشارات الدخول الجديدة."
                elif command=="/resume": self.store.set("paused",False); text="▶️ تم استئناف إشارات الدخول الجديدة."
            if text: self.store.enqueue("command:"+str(uid),"command",text,now.timestamp(),expires=now.timestamp()+300)
            if isinstance(uid,int): self.store.set("update_offset",uid+1)

def run(args):
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store=Store(args.db); telegram=Telegram(args.telegram_token,args.telegram_chat); market=Market(args.twelve_key); news=NewsGuard(store); stop=start_worker(args.db,args.twelve_key)
    try:
        LOG.info("starting version=%s",VERSION)
        store.enqueue('release:2.6.3:messages','release',
                      '✅ <b>ترتيب رسائل بوت ليث صار مفعّل</b>\n\n'
                      '🟢🔴 دخول واضح: سعر، وقف، هدفان.\n'
                      '🔎 تحديث كل 5د مرتبط برسالة الإشارة الأصلية.\n'
                      '🎯 الهدف و🚨 الطوارئ برسائل مميزة؛ تغني عن التحديث المكرر بنفس الفترة.\n\n'
                      'عند عدم وجود إشارة، يستمر ملخص السوق كل 15د وتحديثه كل 5د.\n'
                      'كل إشارة غير مضمونة؛ الترجيح الأولي موضّح بخطر مرتفع.',time.time(),expires=time.time()+3600)
        while True:
            now=datetime.now(UTC)
            try: app=App(store,market,telegram,news,args.cooldown); app.commands(now); app.cycle(now); dispatch(store,telegram,market=market)
            except Exception: LOG.exception("cycle_failed")
            time.sleep(args.interval)
    finally: stop.set(); store.close()

def parser():
    p=argparse.ArgumentParser(); p.add_argument('--db',default=os.getenv('DB_PATH','/data/laith.db')); p.add_argument('--telegram-token',default=os.getenv('TELEGRAM_BOT_TOKEN')); p.add_argument('--telegram-chat',default=os.getenv('TELEGRAM_CHAT_ID')); p.add_argument('--twelve-key',default=os.getenv('TWELVE_DATA_API_KEY')); p.add_argument('--interval',type=int,default=int(os.getenv('CHECK_INTERVAL_SECONDS','20'))); p.add_argument('--cooldown',type=int,default=int(os.getenv('SIGNAL_COOLDOWN_MINUTES','60'))); return p

if __name__=='__main__': run(parser().parse_args())
