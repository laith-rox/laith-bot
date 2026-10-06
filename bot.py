"""Laith Gold Signals v2: persistent monitoring and Telegram alerts only."""
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
from timing import DecisionClock, decision_metadata
from safety_monitor import start_safety_worker

VERSION = "3.0.3"
UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
LOG = logging.getLogger("laith")

def entry_window(now):
    local = now.astimezone(LOCAL)
    return local.weekday() < 5

def daily_risk_blocked(store, now, limit=3.0):
    today=now.astimezone(LOCAL).date(); total=0.0
    for trade in store.completed():
        if datetime.fromtimestamp(trade["closed"],LOCAL).date()==today:
            total += trade["r"] if trade.get("r") is not None else -1.0
    return total <= -limit

class App:
    def __init__(self,store,market,telegram,news,cooldown=240):
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
        """v3: no periodic 5-minute Telegram messages."""
        return

    def us_hourly_recommendation(self, decision, now):
        """One market recommendation per hour during the regular New York session."""
        ny = now.astimezone(NEW_YORK)
        if ny.weekday() >= 5:
            return
        minute = ny.hour * 60 + ny.minute
        opened, closed = 9 * 60 + 30, 16 * 60
        if not opened <= minute < closed:
            return
        slot = (minute - opened) // 60
        event_id = f"us-hourly:{ny.date().isoformat()}:{slot}"
        if self.store.db.execute("SELECT 1 FROM outbox WHERE id=?", (event_id,)).fetchone():
            return
        side = decision.get("side", "WAIT")
        buy, sell = decision.get("buy", "—"), decision.get("sell", "—")
        price = decision.get("price")
        if side == "BUY":
            view = "BUY — ترجيح شراء"
        elif side == "SELL":
            view = "SELL — ترجيح بيع"
        else:
            view = "WAIT — انتظار"
        price_text = f"{float(price):.2f}" if isinstance(price, (int, float)) else "—"
        msg = (
            "🇺🇸 <b>توصية الساعة — جلسة نيويورك</b>\n"
            f"الاتجاه: <b>{view}</b>\n"
            f"السعر المرجعي: <b>{price_text}</b>\n"
            f"شروط الشراء: <b>{buy}/7</b> | البيع: <b>{sell}/7</b>\n"
            "هذه توصية سوق وليست صفقة رسمية جديدة؛ الصفقة الرسمية لها دورة مستقلة كل 4 ساعات."
        )
        self.store.enqueue(event_id, "report", msg, now.timestamp(), expires=now.timestamp()+3600)
        LOG.info("us_hourly_recommendation_prepared slot=%s side=%s", slot, side)

    def cycle(self,now,clock=None):
        clock=clock or DecisionClock(now); epoch=now.timestamp(); self.store.set("heartbeat",epoch); active=self.store.active()
        if not entry_window(now) and not active and not self.store.get("early_watch"):
            self.store.set("last_analysis",{"side":"WAIT","reason":"outside_entry_window"}); return
        try: bars=self.market.fetch(now)
        except DataError as exc:
            reason=str(exc); self.store.set("last_error",reason); self.periodic_reports({"side":"WAIT","reason":reason},[],clock.now(),reason); return
        now=clock.now(); epoch=now.timestamp()
        if active and active["status"]!="pending":
            updated,events=advance_trade(active,bars)
            if not updated.get('protection_rule') and updated['status'] != 'closed':
                updated.update(protection_rule='staged-v1',protection_since=epoch)
            rendered=[]
            for e in events:
                kind=e['kind']
                key=kind+':'+str(int(e['time'])) if kind=='protect' else kind
                view=dict(updated,stop=e['stop']) if kind=='protect' else updated
                rendered.append((key,transition(view,kind)))
            self.store.save_transition(updated,rendered,epoch)
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
        official_slot = int(now.astimezone(LOCAL).timestamp() // (4 * 3600))
        if self.store.get("paused",False): reason="paused"
        elif active: reason="active_signal"
        elif not entry_window(now): reason="outside_entry_window"
        elif not allowed_news: reason=news_reason
        elif daily_risk_blocked(self.store,now): reason="daily_risk_limit"
        elif self.store.get("official_4h_slot") == official_slot: reason="official_4h_slot_used"
        elif epoch-self.store.get("last_signal_at",0)<self.cooldown*60: reason="cooldown"
        elif decision.get("bar") and self.store.get("evaluated_bar")==decision["bar"]: reason="already_evaluated"
        else: reason=None
        if decision.get("bar"): self.store.set("evaluated_bar",decision["bar"])
        if reason: decision=dict(decision,model_side=original_side,side="WAIT",reason=reason)
        self.store.record(now,decision,bars)
        LOG.info("analysis side=%s reason=%s buy=%s sell=%s closed_5m=%s last_close=%s",decision["side"],decision.get("reason"),raw_decision.get("buy"),raw_decision.get("sell"),len(bars),bars[-1].end.isoformat())
        if decision["side"] in ("BUY","SELL"):
            try:
                # A closed 5m candle remains usable briefly after its close. The provider's
                # exchange-rate timestamp can lag even while the candle feed is current.
                # Prefer the live provider quote, but fall back to the latest *fresh closed*
                # candle only; never bypass genuinely stale market data.
                require_fresh(bars,clock.now(),180)
                try:
                    quote=self.market.quote(clock.now)
                    quote_fallback=False
                except DataError as quote_error:
                    if str(quote_error) not in ('market_quote_stale','market_quote_unavailable','market_quote_invalid'):
                        raise
                    fallback_now=clock.now()
                    age=require_fresh(bars,fallback_now,180)
                    quote={'price':bars[-1].close,'time':bars[-1].end.timestamp(),
                           'source':'latest closed 5m'}
                    quote_fallback=True
                    LOG.warning('entry_quote_fallback live_reason=%s closed_age=%.1f',
                                str(quote_error),age)
                now=clock.now(); epoch=now.timestamp()
                require_fresh(bars,now,180)
                if not entry_window(now): raise DataError('outside_entry_window')
                tolerance=min(1.0,decision['atr']*0.25)
                shift=quote['price']-decision['price']
                if abs(shift)>tolerance: raise DataError('market_price_moved')
                decision=dict(decision)
                for field in ('price','sl','tp1','tp2'): decision[field]+=shift
                trade=make_trade(decision,now)
                trade.update(protection_rule='staged-v1',protection_since=epoch)
                trade.update(entry_buy=decision.get('buy'),entry_sell=decision.get('sell'),
                             quote_time=quote['time'],quote_source=quote['source'],
                             price_tolerance=tolerance, official_4h_slot=official_slot,
                             entry_expires=min(quote['time']+(180 if quote_fallback else 90),bars[-1].end.timestamp()+180))
                if not 0 <= epoch-quote['time'] <= (180 if quote_fallback else 90):
                    raise DataError('market_quote_stale')
                if epoch >= trade['entry_expires']:
                    raise DataError('market_quote_stale')
                prepared=self.store.prepare_entry(trade,entry(trade,decision),epoch)
                if prepared:
                    LOG.info('official_4h_entry_prepared slot=%s id=%s price=%.2f source_age=%.1f',
                             official_slot,trade['id'],trade['entry'],epoch-quote['time'])
                else:
                    LOG.info('official_4h_entry_not_prepared slot=%s reason=store_rejected',official_slot)
            except DataError as exc:
                reason=str(exc); self.store.set('last_error',reason)
                LOG.warning('entry_blocked reason=%s',reason)
        # v2.9: Quick/fast entry messages are disabled; official entries only.
        self.periodic_reports(raw_decision,bars,now,reason if reason not in (None,"already_evaluated") else None)

    def commands(self,now):
        offset=self.store.get("update_offset",0); updates=self.telegram.read("getUpdates",offset=offset,timeout=0,allowed_updates='["message"]',limit=20)
        if not isinstance(updates,list): return
        for update in updates:
            uid=update.get("update_id"); message=update.get("message",{}); chat=message.get("chat",{}); sender=message.get("from",{})
            authorized=chat.get("type")=="private" and str(chat.get("id"))==self.telegram.chat_id and str(sender.get("id"))==self.telegram.chat_id
            words=message.get("text","").split(); command=words[0].split("@")[0].lower() if words else ""; text=None
            group_setup=(chat.get("type") in ("group","supergroup") and command=="/emergencyhere"
                         and str(sender.get("id"))==self.telegram.chat_id and not sender.get("is_bot",False))
            if group_setup:
                self.store.set("emergency_chat_id",str(chat.get("id")))
                outcome=self.telegram.send_to(str(chat.get("id")),"🚨 تم ربط مجموعة إنذارات الطوارئ — بوت ليث")
                LOG.info("emergency_group_setup status=%s error=%s",outcome.status,outcome.error)
            if authorized:
                if command in ("/start","/help"): text="🥇 بوت ليث لإشارات الذهب ومتابعتها.\n/status حالة البوت\n/pause إيقاف الدخول\n/resume استئناف الدخول"
                elif command=="/status": text=status(self.store)
                elif command=="/stats": text=stats(self.store)
                elif command=="/testalert": text="🚨 اختبار إنذار الطوارئ — بوت ليث"
                elif command=="/pause": self.store.set("paused",True); text="⏸️ تم إيقاف إشارات الدخول الجديدة."
                elif command=="/resume": self.store.set("paused",False); text="▶️ تم استئناف إشارات الدخول الجديدة."
            if text: self.store.enqueue("command:"+str(uid),"command",text,now.timestamp(),expires=now.timestamp()+300)
            if isinstance(uid,int): self.store.set("update_offset",uid+1)

def run(args):
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store=Store(args.db); telegram=Telegram(args.telegram_token,args.telegram_chat); market=Market(args.twelve_key); news=NewsGuard(store)
    repaired=store.reconcile_official_slot(time.time())
    if repaired: LOG.warning("official_4h_slot_repaired previous=%s",repaired)
    safety_stop=start_safety_worker(args.db,args.twelve_key,args.telegram_token,args.telegram_chat)
    try:
        LOG.info("starting version=%s",VERSION)
        store.enqueue('release:3.0.2:official-4h-only','release',
                      '✅ <b>بوت ليث v3.0.2 — صفقة رسمية كل 4 ساعات</b>\n\n'
                      'صفقة رسمية واحدة كحد أقصى في كل دورة 4 ساعات، عند توفر بيانات سوق حديثة وعدم وجود صفقة رسمية مفتوحة.\n'
                      'لا Quick/fast، لا تقارير دخول كل 15د، ولا توصيات نيويورك كل ساعة.\n'
                      'الطوارئ والحماية الحدثية تبقى فعّالة للصفقة الرسمية.\n'
                      'الإشارات غير مضمونة ولا ينفّذ البوت أوامر عند الوسيط.',time.time(),expires=time.time()+3600)
        while True:
            now=datetime.now(UTC)
            try:
                app=App(store,market,telegram,news,args.cooldown)
                try: app.commands(now)
                except Exception as exc: LOG.warning("telegram_commands_failed category=%s",type(exc).__name__)
                app.cycle(datetime.now(UTC))
                dispatch(store,telegram,market=market)
            except Exception: LOG.exception("cycle_failed")
            time.sleep(args.interval)
    finally: safety_stop.set(); store.close()

def parser():
    p=argparse.ArgumentParser(); p.add_argument('--db',default=os.getenv('DB_PATH','/data/laith.db')); p.add_argument('--telegram-token',default=os.getenv('TELEGRAM_BOT_TOKEN')); p.add_argument('--telegram-chat',default=os.getenv('TELEGRAM_CHAT_ID')); p.add_argument('--twelve-key',default=os.getenv('TWELVE_DATA_API_KEY')); p.add_argument('--interval',type=int,default=int(os.getenv('CHECK_INTERVAL_SECONDS','20'))); p.add_argument('--cooldown',type=int,default=int(os.getenv('SIGNAL_COOLDOWN_MINUTES','240'))); return p

if __name__=='__main__': run(parser().parse_args())
