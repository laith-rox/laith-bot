"""Retrospective comparison on saved prices; never relabel development data as validation."""
from datetime import datetime, timedelta
import json
import logging
import time

from fast import analyze_fast
from fast_candidate import RULE, analyze_candidate
from fast_research import simulate_fast, cost_summary
from market import Bar, DataError, UTC
from news import week_start

LOG = logging.getLogger('laith')
COMPARE_COSTS = (.5, 1.0)


def read_trades(store, stem='fast', since=0):
    if stem not in ('fast', 'fast2'):
        raise ValueError('unknown_paper_stream')
    rows = store.db.execute(f'SELECT data FROM {stem}_paper').fetchall()
    trades = [json.loads(r[0]) for r in rows]
    return sorted((t for t in trades if t['announced'] >= since), key=lambda t:(t['closed'],t['id']))


def comparison_summary(result):
    old = result['later_segment']['baseline']['cost_scenarios'][-1]
    new = result['later_segment']['candidate']['cost_scenarios'][-1]
    return ('🧪 <b>مقارنة تعديل الدخول السريع — محاكاة فقط</b>\n'
            f"على نفس الجزء الزمني والتكلفة المفترضة 1$ للأونصة:\n"
            f"الطريقة السابقة: {old['measured']} متابعة، محصلة {old['net_r']:+.2f}R.\n"
            f"تأكيد البنية وإعادة الاختبار: {new['measured']} متابعة، محصلة {new['net_r']:+.2f}R.\n"
            'هذا فحص تطوير على تاريخ سبق الاطلاع عليه، وليس إثباتًا للربحية. '
            'الطريقتان تُتابعان ورقيًا على الأسعار القادمة للمقارنة. لا إشارات دخول سريعة. /fast')


def compare_saved(store, now):
    if store.get('fast_comparison_rule') == RULE:
        return
    cache = store.get('calendar')
    start = week_start(now).astimezone(UTC)
    if not cache or cache['week'] != week_start(now).isoformat():
        raise DataError('comparison_calendar_unavailable')
    rows = store.db.execute('SELECT time,open,high,low,close FROM fast_bars '
                            'WHERE time>=? AND time<? ORDER BY time',
                            ((start-timedelta(days=2)).timestamp(),now.timestamp())).fetchall()
    bars = [Bar(datetime.fromtimestamp(r[0],UTC),*r[1:],1) for r in rows]
    bars = [b for b in bars if b.end <= now]
    covered = [b for b in bars if b.start >= start]
    if len(covered) < 600:
        raise DataError('comparison_saved_history_insufficient')
    split = covered[int(len(covered)*.7)].start
    result = {'candidate_rule':RULE, 'mode':'DEVELOPMENT_COMPARISON_NOT_HOLDOUT',
              'sample_start':covered[0].start.isoformat(), 'sample_end':covered[-1].end.isoformat(),
              'candles':len(covered), 'later_segment_from':split.isoformat(),
              'costs':'Hypothetical total spread/slippage; broker commission is unknown',
              'periods':{}, 'later_segment':{}, 'recorded_paper_review':[]}
    for name, analyzer in (('baseline',analyze_fast),('candidate',analyze_candidate)):
        result['periods'][name] = simulate_fast(bars,COMPARE_COSTS,cache['events'],
                                               start_from=covered[0].start,analyzer=analyzer)
        result['later_segment'][name] = simulate_fast(bars,COMPARE_COSTS,cache['events'],
                                                    start_from=split,analyzer=analyzer)
    # Review all recorded baseline outcomes, including winners the new rule would skip.
    for t in read_trades(store):
        at = datetime.fromisoformat(t['bar'])
        past = [b for b in bars if b.end <= at]
        try:
            d = analyze_candidate(past[-600:],at+timedelta(seconds=8))
            decision = {'side':d['side'],'reason':d['reason'],'context':d.get('context')}
        except DataError as exc:
            decision = {'side':'UNAVAILABLE','reason':str(exc)}
        result['recorded_paper_review'].append({'id':t['id'],'entry_side':t['side'],
            'decision_bar':t['bar'],'outcome':t['outcome'],'gross_r':t['r'],'candidate':decision})
    result['decision'] = 'PAPER_COMPARISON_ONLY_NO_AUTOMATIC_ACTIVATION'
    with store.db:
        store._set('fast_comparison',result)
        store._set('fast_comparison_rule',RULE)
        if store.get('fast_comparison_started_at') is None:
            store._set('fast_comparison_started_at',time.time())
    LOG.info('fast_comparison_result %s',json.dumps(result,ensure_ascii=False,allow_nan=False))
    store.enqueue('comparison:'+RULE,'service',comparison_summary(result),time.time(),expires=time.time()+86400)


def forward_status(store):
    since = store.get('fast_comparison_started_at')
    if since is None:
        return '\nمقارنة طريقة إعادة الاختبار قيد التجهيز.'
    text = '\n<b>المقارنة الورقية على الأسعار القادمة منذ نشر التعديل</b>\n'
    for stem,name in (('fast','السابقة'),('fast2','إعادة الاختبار')):
        trades = read_trades(store,stem,since)
        totals = cost_summary(trades,COMPARE_COSTS)
        text += (f"{name}: {len(trades)} منتهية | "
                 f"بتكلفة 0.5$: {totals[0]['net_r']:+.2f}R | بتكلفة 1$: {totals[1]['net_r']:+.2f}R\n")
        text += f"نتائج مستبعدة لعدم اليقين: {sum(t['r'] is None for t in trades)}\n"
    return text+'التكاليف افتراضية؛ لا تنفيذ وسيط ولا ضمان. R نسبة إلى مخاطرة الوقف الأول.'
