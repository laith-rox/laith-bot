"""Event-triggered, standalone warnings from fresh closed one-minute bars.

This worker never modifies a signal/order/stop or evaluates new entries.
"""
from datetime import datetime
from html import escape
import logging
import threading
import time

from engine import atr, ema
from fast import MinuteMarket
from market import DataError, require_fresh, UTC
from messages import local_time
from storage import Store
from transport import Telegram, dispatch

LOG=logging.getLogger('laith')


def evaluate_warning(trade,bars,now,previous=None):
    require_fresh(bars,now,90)
    if len(bars)<22 or any(b.minutes!=1 for b in bars[-22:]):
        raise DataError('safety_history_insufficient')
    if any((b.start-a.start).total_seconds()!=60 for a,b in zip(bars[-22:-1],bars[-21:])):
        raise DataError('safety_data_gap')
    state=dict(previous or {})
    last=bars[-1]; stamp=last.end.timestamp()
    if (last.start.timestamp() < (trade.get('announced') or trade['created'])
            or stamp <= state.get('stamp',0)):
        return None,state
    direction=1 if trade['side']=='BUY' else -1
    price=last.close; volatility=atr(bars[-22:])
    threshold=max(.5,.75*volatility)
    # Only observations actually seen after entry contribute to the peak.
    old_peak=state.get('peak',price)
    peak=max(old_peak,price) if direction==1 else min(old_peak,price)
    retrace=direction*(peak-price)
    closes=[b.close for b in bars[-22:]]
    fast,slow=ema(closes,9)[-1],ema(closes,21)[-1]
    prior=bars[-8:-2]
    boundary=min(b.low for b in prior) if direction==1 else max(b.high for b in prior)
    broken=all(direction*(b.close-boundary)<-.1*volatility for b in bars[-2:])
    counter=direction*(fast-slow)<0
    observed=0
    if direction*(price-trade['stop'])<=0:
        observed=3
    elif broken and counter and bars[-2].start.timestamp()>=(trade.get('announced') or trade['created']):
        observed=2
    elif retrace>=threshold and direction*(last.close-bars[-2].close)<0:
        observed=1
    old_level=state.get('level',0)
    recovery = state.get('recovery',0)+1 if observed==0 and retrace<threshold*.5 and direction*(price-fast)>0 else 0
    if recovery>=2:
        if old_level: state['episode']=state.get('episode',0)+1
        old_level=0
    state.update(stamp=stamp,peak=peak,recovery=recovery,level=max(old_level,observed))
    if observed<=old_level: return None,state
    kind={1:'correction',2:'reversal',3:'stop'}[observed]
    return {'kind':kind,'price':price,'stamp':stamp,'retrace':retrace,
            'boundary':boundary,'episode':state.get('episode',0)},state


def warning_message(trade,event):
    movement = '⬇️ هابط' if trade['side']=='BUY' else '⬆️ صاعد'
    observed = 'رُصد تراجع هابط ⬇️ ضد الشراء' if trade['side']=='BUY' else 'رُصد ارتداد صاعد ⬆️ ضد البيع'
    labels={'correction':'⚠️ ' + observed,
            'reversal':'🚨 خطر انعكاس ' + movement + ': كسر قصير وزخم معاكس',
            'stop':'🚨 رُصد تجاوز الوقف في بيانات المصدر'}
    side='شراء' if trade['side']=='BUY' else 'بيع'
    action=('تصحيح محتمل؛ استمرار الحركة غير مؤكد، وليس إشارة دخول عكسية.' if event['kind']=='correction' else
            'راجع سعر وسيطك والوقف فورًا؛ لا تدخل عكسًا تلقائيًا.')
    return (f"<b>{labels[event['kind']]}</b>\n{side} | <code>{escape(trade['id'])}</code>\n"
            f"إغلاق الدقيقة: <b>{event['price']:.2f}</b> | {local_time(event['stamp'])} فلسطين\n"
            f"الوقف المقترح: <b>{trade['stop']:.2f}</b>\n{action}\n"
            'Twelve Data؛ ليس سعر وسيطك الحي. تحذير احتمالي، لا إغلاق آلي.')


def monitor(store,bars,now):
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        trade=store.active()
        if not trade or trade['status'] not in ('active','uncertain_delivery'): return
        key='safety:'+trade['id']
        event,state=evaluate_warning(trade,bars,now,store.get(key))
        store._set(key,state)
        store._set('safety_status',{'ok':True,'checked':now.timestamp(),
                                  'source_time':bars[-1].end.timestamp()})
        if event:
            event_id=f"rapid:{trade['id']}:{event['episode']}:{event['kind']}"
            store._enqueue(event_id,'emergency',warning_message(trade,event),now.timestamp(),
                           trade['id'],now.timestamp()+90)
            LOG.info('safety_event id=%s kind=%s source_age=%.1f',event_id,event['kind'],
                     now.timestamp()-event['stamp'])


def run(path,key,token,chat_id,stop):
    store=Store(path); market=MinuteMarket(key); telegram=Telegram(token,chat_id)
    next_fetch=0
    LOG.info('safety_worker_started interval=60 source=closed_1m standalone=true')
    try:
        while not stop.is_set():
            try:
                now=datetime.now(UTC); trade=store.active()
                if trade and trade['status'] in ('active','uncertain_delivery') and time.time()>=next_fetch:
                    next_fetch=time.time()+60
                    try:
                        bars=market.fetch(now,size=60)
                        monitor(store,bars,datetime.now(UTC))
                        LOG.info('safety_checked source=%s',bars[-1].end.isoformat())
                    except DataError as exc:
                        previous=store.get('safety_status',{})
                        store.set('safety_status',{'ok':False,'checked':time.time(),'reason':str(exc),
                                                  'signal_id':trade['id']})
                        if previous.get('ok',True) or previous.get('signal_id')!=trade['id']:
                            event_id='rapid:'+trade['id']+':unavailable:'+str(int(time.time()))
                            store.enqueue(event_id,'emergency',
                                '⚠️ تعذّر تحديث مراقبة الدقيقة\nالمرجع: <code>'+escape(trade['id'])+
                                '</code>\nالبيانات متأخرة أو غير متاحة؛ لا تعتمد على الطوارئ وحدها لتنفيذ وقفك.',
                                time.time(),signal_id=trade['id'],expires=time.time()+180)
                        if str(exc)=='minute_quota_reached': next_fetch=time.time()+900
                        LOG.warning('safety_unavailable reason=%s',str(exc))
                # Flush alerts independently, including five-minute structural warnings.
                dispatch(store,telegram,only_kind='emergency',limit=3)
            except Exception as exc:
                LOG.error('safety_cycle_failed category=%s',type(exc).__name__)
            stop.wait(2)
    finally:
        store.close()


def start_safety_worker(path,key,token,chat_id):
    stop=threading.Event()
    threading.Thread(target=run,args=(path,key,token,chat_id,stop),
                     daemon=True,name='signal-safety').start()
    return stop
