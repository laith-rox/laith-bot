"""Fixed delay sensitivity on saved prices, plus a separate measured-clock cohort."""
from datetime import datetime, timedelta
import json
import logging

from fast import analyze_fast
from fast_candidate import analyze_candidate, RULE
from fast_research import simulate_fast
from market import Bar, UTC
from news import archive_calendar
from timing import EXECUTION_MODEL

LOG = logging.getLogger('laith')


def start_timing_cohort(store, now):
    if store.get('fast_timing_model') == EXECUTION_MODEL:
        return
    # Old active watches retain their original model; unfilled legacy decisions expire.
    with store.db:
        for stem in ('fast','fast2'):
            store._set(stem+'_paper_pending',None)
        store._set('fast_timing_model',EXECUTION_MODEL)
        store._set('fast_timing_started_at',now.timestamp())
    LOG.info('fast_timing_cohort_started model=%s since=%s',EXECUTION_MODEL,now.isoformat())


def audit_saved(store, now):
    store.set('fast_timing_audit_attempt',now.timestamp())
    archive_calendar(store,store.get('calendar'))
    caches = [json.loads(r[0]) for r in store.db.execute(
        "SELECT value FROM kv WHERE key LIKE 'calendar_archive:%'")]
    for cache in sorted(caches,key=lambda c:c['week'],reverse=True):
        start = datetime.fromisoformat(cache['week'])
        end = min(start+timedelta(days=7),now)
        if end <= start:
            continue
        key = 'timing_audit:'+EXECUTION_MODEL+':'+cache['week']
        if store.get(key):
            return
        rows = store.db.execute('SELECT time,open,high,low,close FROM fast_bars '
                                'WHERE time>=? AND time<? ORDER BY time',
                                ((start-timedelta(days=2)).timestamp(),end.timestamp())).fetchall()
        bars = [Bar(datetime.fromtimestamp(r[0],UTC),*r[1:],1) for r in rows]
        bars = [b for b in bars if b.end <= end]
        covered = [b for b in bars if b.start >= start]
        if len(covered) < 600:
            continue
        result = {'execution_model':EXECUTION_MODEL,'candidate_rule':RULE,
                  'mode':'DEVELOPMENT_DELAY_SENSITIVITY_NOT_VALIDATION',
                  'calendar_week':cache['week'],'calendar_snapshot_at':cache['fetched'],
                  'calendar_limit':'Archived schedule snapshot; not a point-in-time news revision archive',
                  'sample_start':covered[0].start.isoformat(),'sample_end':covered[-1].end.isoformat(),
                  'candles':len(covered),'delays':'Fixed hypothetical observation delays, not measured broker latency',
                  'costs':'Hypothetical round-trip quote dollars per ounce; actual broker costs unknown',
                  'scenarios':{},'decision':'PAPER_ONLY_NO_AUTOMATIC_ACTIVATION'}
        for name,analyzer in (('baseline',analyze_fast),('candidate',analyze_candidate)):
            result['scenarios'][name] = {
                str(delay):simulate_fast(bars,(.5,1.0),cache['events'],
                    start_from=covered[0].start,analyzer=analyzer,observation_lag_seconds=delay)
                for delay in (8,68)}
        with store.db:
            store._set(key,result)
            store._set('fast_timing_audit',result)
            store._set('fast_timing_audit_status','completed_development_only')
        LOG.info('fast_timing_audit_result %s',json.dumps(result,allow_nan=False))
        return
    store.set('fast_timing_audit_status','awaiting_saved_prices_with_matching_calendar')
    LOG.info('fast_timing_audit_unavailable reason=awaiting_saved_prices_with_matching_calendar')
