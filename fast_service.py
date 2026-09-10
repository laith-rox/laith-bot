"""Isolated research worker: one-minute paper monitoring, never trading alerts/orders."""
from datetime import datetime, timedelta
import json
import logging
import threading
import time

from fast import MinuteMarket, analyze_fast, paper_fill, advance_fast, fast_window
from fast_research import evaluate, summary
from market import DataError, UTC
from news import NewsGuard, week_start
from storage import Store
from messages import LOCAL

LOG = logging.getLogger('laith')


def fast_status(store):
    result = store.get('fast_research')
    status = store.get('fast_state', 'بانتظار الفحص')
    text = '🧪 <b>مسار الدقيقة التجريبي</b>\nوضع مراقبة ورقية؛ لا إشارات دخول منه.\n'
    text += 'الحالة: ' + status + '\n'
    if result:
        sample = result['holdout']['cost_scenarios'][-1]
        text += (f"عينة لاحقة: {sample['measured']} | نتيجة {sample['net_r']:+.2f}R\n"
                 f"بتكلفة مفترضة {sample['round_trip_dollars_per_ounce']}$ للأونصة للدورة، ليست سبريد حسابك.\n")
    paper = store.get('fast_paper_stats', {'closed':0, 'gross_r':0, 'excluded':0})
    text += (f"المتابعة الورقية المباشرة: {paper['closed']} منتهية؛ مجموع {paper['gross_r']:+.2f}R قبل التكاليف.\n"
             'هدف النموذج 5$ بسعر الأونصة، مدة أقصاها 20د، وفحص كل دقيقة بعد 20:00 حتى 23:30 فلسطين. '
             'نتائج افتراضية وليست ربح حساب أو دليلًا على النجاح مستقبلاً.')
    return text


def finish_paper(store, trade):
    with store.db:
        changed = store.db.execute('INSERT OR IGNORE INTO fast_paper(id,data) VALUES (?,?)',
                         (trade['id'],json.dumps(trade,allow_nan=False))).rowcount
        if changed:
            stats = store.get('fast_paper_stats', {'closed':0,'gross_r':0,'excluded':0})
            stats['closed'] += 1
            stats['excluded'] += int(trade['r'] is None)
            stats['gross_r'] += trade['r'] or 0
            store._set('fast_paper_stats',stats)
            daily = store.get('fast_paper_daily', {})
            date = datetime.fromtimestamp(trade['closed'],LOCAL).date().isoformat()
            daily[date] = daily.get(date,0)+(trade['r'] if trade['r'] is not None else -1)
            store._set('fast_paper_daily',daily)
        store._set('fast_paper_watch',None)
    LOG.info('fast_paper_closed id=%s outcome=%s r=%s',trade['id'],trade['outcome'],trade['r'])


def paper_cycle(store, market, news, now):
    active = store.get('fast_paper_watch')
    if not fast_window(now) and not active:
        return
    if store.get('paused',False) and not active:
        store.set('fast_paper_pending',None)
        return
    bars = market.fetch(now)
    with store.db:
        store.db.executemany('INSERT OR IGNORE INTO fast_bars(time,open,high,low,close) VALUES (?,?,?,?,?)',
                  [(b.start.timestamp(),b.open,b.high,b.low,b.close) for b in bars])
    if active:
        active = advance_fast(active,bars)
        if active['status'] == 'closed':
            finish_paper(store,active)
            active = None
        else:
            store.set('fast_paper_watch',active)
    allowed, _, _ = news.check(now)
    today = now.astimezone(LOCAL).date().isoformat()
    allowed = allowed and not store.get('paused',False) and store.get('fast_paper_daily',{}).get(today,0) > -3
    pending = store.get('fast_paper_pending')
    if pending and not active:
        stamp = pending['time']
        choices = [b for b in bars if stamp < b.start.timestamp() <= stamp+120]
        if choices and allowed and fast_window(choices[0].start):
            active = paper_fill(pending['decision'],choices[0])
            if active:
                store.set('fast_last_paper_entry',active['announced'])
                active = advance_fast(active, bars)
                if active['status'] == 'closed':
                    finish_paper(store,active)
                    active = None
                else:
                    store.set('fast_paper_watch',active)
                    LOG.info('fast_paper_open id=%s side=%s reference=%.2f',active['id'],active['side'],active['entry'])
        if choices or not allowed or now.timestamp()-stamp > 180:
            store.set('fast_paper_pending',None)
    if (active or store.get('fast_paper_pending') or not allowed or not fast_window(now)
            or now.timestamp()-store.get('fast_last_paper_entry',0) < 300):
        return
    d = analyze_fast(bars,now)
    store.set('fast_last_analysis', d)
    store.set('fast_state','شموع الدقيقة متاحة؛ المراقبة الورقية تعمل')
    if d['side'] in ('BUY','SELL') and store.get('fast_evaluated_bar') != d['bar']:
        store.set('fast_paper_pending',{'decision':d,'time':now.timestamp()})
    store.set('fast_evaluated_bar',d['bar'])


def run(path, key, stop):
    store = Store(path)
    market, news = MinuteMarket(key), NewsGuard(store)
    try:
        store.db.executescript('''CREATE TABLE IF NOT EXISTS fast_bars(
            time REAL PRIMARY KEY, open REAL,high REAL,low REAL,close REAL);
            CREATE TABLE IF NOT EXISTS fast_paper(id TEXT PRIMARY KEY,data TEXT NOT NULL);''')
        now = datetime.now(UTC)
        run_id = 'fast-v1:' + week_start(now).isoformat()
        if store.get('fast_research_run') != run_id and time.time()-store.get('fast_probe_attempt',0) >= 3600:
            store.set('fast_probe_attempt',time.time())
            store.set('fast_state','فحص صلاحية الدقيقة وتقييم تاريخي جارٍ')
            try:
                news.check(now)
                cache = store.get('calendar')
                if (not cache or cache['week'] != week_start(now).isoformat()
                        or not 0 <= now.timestamp()-cache['fetched'] <= 7200):
                    raise DataError('fast_calendar_not_ready')
                result, bars = evaluate(market,now,cache['events'])
                with store.db:
                    store.db.executemany('INSERT OR IGNORE INTO fast_bars(time,open,high,low,close) VALUES (?,?,?,?,?)',
                                  [(b.start.timestamp(),b.open,b.high,b.low,b.close) for b in bars])
                    store._set('fast_research',result)
                    store._set('fast_research_run',run_id)
                    store._set('fast_state','التقييم مكتمل؛ المسار تجريبي فقط')
                LOG.info('fast_research_result %s',json.dumps(result,ensure_ascii=False,allow_nan=False))
                store.enqueue(run_id,'service',summary(result),time.time(),expires=time.time()+86400)
            except DataError as exc:
                store.set('fast_state',str(exc))
                LOG.warning('fast_research_unavailable reason=%s',str(exc))
        next_cycle = 0
        while not stop.is_set():
            now = datetime.now(UTC)
            if now.timestamp() >= next_cycle:
                try:
                    paper_cycle(store,market,news,now)
                except DataError as exc:
                    store.set('fast_state',str(exc))
                    LOG.warning('fast_paper_unavailable reason=%s',str(exc))
                next_cycle = (int(time.time())//60+1)*60+8
            stop.wait(2)
    except Exception as exc:
        LOG.error('fast_worker_stopped category=%s',type(exc).__name__)
        store.set('fast_state','توقفت التجربة؛ راجع سجل الخدمة')
    finally:
        store.close()


def start_worker(path,key):
    stop = threading.Event()
    thread = threading.Thread(target=run,args=(path,key,stop),daemon=True,name='fast-research')
    thread.start()
    return stop
