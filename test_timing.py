"""Regression tests for observed decision time, stale data and honest paper cohorts."""
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from bot import App
from fast import paper_fill
from fast_compare import forward_status
from fast_research import simulate_fast
from fast_service import paper_cycle, cycle_rule
from fast_timing import start_timing_cohort, audit_saved
from market import Bar, UTC
from news import NewsGuard, archive_calendar, week_start
from storage import Store
from test_bot import NOW, history, response
from test_fast import AT, minutes, fixture_decision
from timing import DecisionClock, EXECUTION_MODEL, decision_metadata


class TimingTests(unittest.TestCase):
    def store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(Path(tmp.name)/'db')
        self.addCleanup(store.close)
        store.db.executescript('CREATE TABLE fast_paper(id TEXT PRIMARY KEY,data TEXT NOT NULL);'
                              'CREATE TABLE fast2_paper(id TEXT PRIMARY KEY,data TEXT NOT NULL);'
                              'CREATE TABLE fast_bars(time REAL PRIMARY KEY,open REAL,high REAL,low REAL,close REAL);')
        return store

    def clock(self, anchor=AT):
        elapsed = [0.]
        return DecisionClock(anchor,lambda:elapsed[0]), elapsed

    def test_market_news_and_analysis_delays_each_block_stale_fast_entries(self):
        for stage in ('market','news','analysis'):
            with self.subTest(stage=stage):
                store = self.store()
                clock, elapsed = self.clock()
                def fetch(*a,**k):
                    elapsed[0] += 75.01 if stage == 'market' else 0
                    return minutes()
                def news_check(*a):
                    elapsed[0] += 75.01 if stage == 'news' else 0
                    return True,'clear',[]
                def analyze(b,n):
                    elapsed[0] += 75.01 if stage == 'analysis' else 0
                    return fixture_decision(b,n)
                with patch('fast_service.analyze_fast',side_effect=analyze), patch('fast_service.analyze_candidate',side_effect=analyze):
                    paper_cycle(store,Mock(fetch=Mock(side_effect=fetch)),Mock(check=Mock(side_effect=news_check)),AT,clock)
                for stem in ('fast','fast2'):
                    self.assertIsNone(store.get(stem+'_paper_pending'))
                    self.assertEqual(store.get(stem+'_timing_status'),'market_closed_candles_stale')

    def test_decision_and_fill_observation_are_separate_and_persist(self):
        store = self.store()
        clock, elapsed = self.clock()
        data = minutes()
        def fetch(*a,**k):
            elapsed[0] += 12
            return data
        def news_check(*a):
            elapsed[0] += 7
            return True,'clear',[]
        def analyze(b,n):
            elapsed[0] += 5
            return fixture_decision(b,n)
        with patch('fast_service.analyze_fast',side_effect=analyze), patch('fast_service.analyze_candidate',side_effect=analyze):
            paper_cycle(store,Mock(fetch=Mock(side_effect=fetch)),Mock(check=Mock(side_effect=news_check)),AT,clock)
        pending = store.get('fast_paper_pending')
        self.assertEqual(pending['time'],(AT+timedelta(seconds=24)).timestamp())
        self.assertEqual(pending['decision']['source_age_at_decision_seconds'],39)
        self.assertEqual(store.get('fast_last_fetch')['request_elapsed_seconds'],12)
        self.assertEqual(store.get('fast2_paper_pending')['time']-pending['time'],5)
        p = pending['decision']['price']
        start = AT.replace(second=0)
        data += [Bar(start+timedelta(minutes=i),p,p+.1,p-.1,p,1) for i in (0,1)]
        observed = start+timedelta(minutes=2,seconds=8)
        fixed, _ = self.clock(observed)
        cycle_rule(store,data,observed,True,[],'fast',Mock(),fixed)
        trade = store.get('fast_paper_watch')
        self.assertEqual(trade['execution_model'],EXECUTION_MODEL)
        self.assertEqual(trade['decision_time'],pending['time'])
        self.assertEqual(trade['announced'],(start+timedelta(minutes=1)).timestamp())
        self.assertEqual(trade['fill_observed_at'],observed.timestamp())
        self.assertGreater(trade['announced'],trade['decision_time'])

    def test_crossing_session_end_during_request_prevents_entry(self):
        store = self.store()
        at = AT.replace(hour=20,minute=29,second=50)
        shift = at.replace(second=15)-AT
        data = [Bar(b.start+shift,b.open,b.high,b.low,b.close,1) for b in minutes()]
        clock, elapsed = self.clock(at)
        def fetch(*a,**k):
            elapsed[0] = 20
            return data
        paper_cycle(store,Mock(fetch=Mock(side_effect=fetch)),Mock(check=Mock(return_value=(True,'clear',[]))),at,clock)
        self.assertIsNone(store.get('fast_paper_pending'))
        self.assertIsNone(store.get('fast2_paper_pending'))

    def test_crossing_news_boundary_during_analysis_prevents_entry(self):
        store = self.store()
        clock, elapsed = self.clock()
        event = {'time':AT.timestamp()+1805}
        store.set('calendar',{'events':[event]})
        def analyze(b,n):
            elapsed[0] += 10
            return fixture_decision(b,n)
        with patch('fast_service.analyze_fast',side_effect=analyze):
            paper_cycle(store,Mock(fetch=Mock(return_value=minutes())),Mock(check=Mock(return_value=(True,'clear',[]))),AT,clock)
        self.assertIsNone(store.get('fast_paper_pending'))
        self.assertIsNone(store.get('fast2_paper_pending'))

    def test_stale_prices_can_close_existing_watch_without_opening_another(self):
        store = self.store()
        data = minutes()
        d = fixture_decision(data,AT)
        p = d['price']
        t = paper_fill(d,Bar(data[-3].start,p,p+.1,p-.1,p,1))
        store.set('fast_paper_watch',t)
        data[-1] = Bar(data[-1].start,p,p+.1,p-2,p-1,1)
        at = AT+timedelta(minutes=2)
        clock,_ = self.clock(at)
        paper_cycle(store,Mock(fetch=Mock(return_value=data)),Mock(check=Mock(return_value=(True,'clear',[]))),at,clock)
        self.assertIsNone(store.get('fast_paper_watch'))
        self.assertEqual(store.db.execute('SELECT count(*) FROM fast_paper').fetchone()[0],1)
        self.assertIsNone(store.get('fast_paper_pending'))

    def test_fill_cannot_use_an_open_at_or_before_actual_decision(self):
        data = minutes()
        d = dict(fixture_decision(data,AT),**decision_metadata(data,AT))
        p = d['price']
        self.assertIsNone(paper_fill(d,Bar(AT,p,p+.1,p-.1,p,1)))
        self.assertIsNotNone(paper_fill(d,Bar(AT+timedelta(seconds=1),p,p+.1,p-.1,p,1)))

    def test_simulated_delay_moves_decision_and_fill_without_future_candles(self):
        results = []
        for delay in (8,68):
            def analyze(b,n):
                self.assertEqual((n-b[-1].end).total_seconds(),delay)
                return fixture_decision(b,n)
            with patch('fast_research.fast_window',return_value=True):
                results.append(simulate_fast(minutes(),[.5],[],analyzer=analyze,
                    include_trades=True,observation_lag_seconds=delay))
        first, later = [r['trades'][0] for r in results]
        self.assertEqual(later['decision_time']-first['decision_time'],60)
        self.assertEqual(later['announced']-first['announced'],60)
        for result in results:
            for t in result['trades']:
                self.assertGreater(t['announced'],t['decision_time'])
                self.assertGreaterEqual(t['fill_observed_at'],t['announced']+60)

    def test_research_cannot_override_freshness_and_rejects_invalid_delay(self):
        with patch('fast_research.fast_window',return_value=True):
            result = simulate_fast(minutes(),[.5],[],analyzer=fixture_decision,observation_lag_seconds=91)
        self.assertEqual(result['signals'],0)
        for bad in (-1,float('nan'),float('inf'),True,'8'):
            with self.assertRaises(ValueError):
                simulate_fast([],[],[],observation_lag_seconds=bad)

    def test_slow_reports_and_entries_recheck_age_after_market_or_news_wait(self):
        for stage in ('market','news'):
            with self.subTest(stage=stage):
                store = self.store()
                clock, elapsed = self.clock(NOW)
                def fetch(*a):
                    elapsed[0] += 106 if stage == 'market' else 0
                    return history()
                def news_check(*a):
                    elapsed[0] += 106 if stage == 'news' else 0
                    return True,'clear',[]
                app = App(store,Mock(fetch=Mock(side_effect=fetch)),Mock(),Mock(check=Mock(side_effect=news_check)))
                app.cycle(NOW,clock)
                self.assertIsNone(store.active())
                self.assertEqual(store.get('last_analysis')['reason'],'market_closed_candles_stale')
                self.assertIsNone(store.get('report_candidate')['side'])
                self.assertIsNone(store.get('report_candidate')['watch'])

    def test_news_guard_uses_completion_time_for_blackout_and_cache_age(self):
        store = self.store()
        clock, elapsed = self.clock(NOW)
        event_at = NOW+timedelta(seconds=1805)
        def get(*a,**k):
            elapsed[0] = 10
            return response([{'title':'test','country':'USD','impact':'High','date':event_at.isoformat()}])
        allowed,reason,_ = NewsGuard(store,Mock(get=Mock(side_effect=get))).check(NOW,clock)
        self.assertFalse(allowed)
        self.assertEqual(reason,'news_blackout')
        self.assertEqual(store.get('calendar')['fetched'],NOW.timestamp()+10)

    def test_week_rollover_during_calendar_request_is_rejected_and_archived(self):
        store = self.store()
        at = (week_start(NOW)+timedelta(days=7,seconds=-5)).astimezone(UTC)
        clock, elapsed = self.clock(at)
        def get(*a,**k):
            elapsed[0] = 10
            return response([{'title':'test','country':'USD','impact':'High','date':NOW.isoformat()}])
        allowed,reason,_ = NewsGuard(store,Mock(get=Mock(side_effect=get))).check(at,clock)
        self.assertFalse(allowed)
        self.assertEqual(reason,'calendar_unavailable')
        self.assertIsNotNone(store.get('calendar_archive:'+week_start(at).isoformat()))

    def test_new_cohort_excludes_legacy_and_survives_restart(self):
        store = self.store()
        store.set('fast_paper_pending',{'time':AT.timestamp()-10})
        store.set('fast_paper_watch',{'id':'legacy-active'})
        start_timing_cohort(store,AT)
        self.assertIsNone(store.get('fast_paper_pending'))
        self.assertEqual(store.get('fast_paper_watch')['id'],'legacy-active')
        start_timing_cohort(store,AT+timedelta(days=1))
        self.assertEqual(store.get('fast_timing_started_at'),AT.timestamp())
        for i,model in enumerate((None,EXECUTION_MODEL)):
            t = {'id':str(i),'announced':AT.timestamp()+120,'closed':AT.timestamp()+300,
                 'decision_time':AT.timestamp()+60,'execution_model':model,
                 'entry':100,'initial_sl':98,'r':1.0 if model else -5.0}
            with store.db:
                store.db.execute('INSERT INTO fast_paper VALUES (?,?)',(t['id'],json.dumps(t)))
        text = forward_status(store)
        self.assertIn('السابقة: 1 منتهية',text)
        self.assertIn('+0.75R',text)
        self.assertIn('إعادة الاختبار: 0 منتهية',text)

    def test_audit_waits_for_calendar_instead_of_assuming_no_news(self):
        store = self.store()
        audit_saved(store,AT)
        self.assertIsNone(store.get('fast_timing_audit'))
        self.assertEqual(store.get('fast_timing_audit_status'),'awaiting_saved_prices_with_matching_calendar')

    def test_audit_can_use_archived_week_without_relabelling_it_as_validation(self):
        store = self.store()
        archive_calendar(store,{'week':week_start(AT).isoformat(),'fetched':AT.timestamp(),'events':[]})
        next_week = AT+timedelta(days=7)
        store.set('calendar',{'week':week_start(next_week).isoformat(),'fetched':next_week.timestamp(),'events':[]})
        with store.db:
            store.db.executemany('INSERT INTO fast_bars VALUES (?,?,?,?,?)',
                [(b.start.timestamp(),b.open,b.high,b.low,b.close) for b in minutes()])
        audit_saved(store,next_week)
        result = store.get('fast_timing_audit')
        self.assertEqual(result['calendar_week'],week_start(AT).isoformat())
        self.assertEqual(result['mode'],'DEVELOPMENT_DELAY_SENSITIVITY_NOT_VALIDATION')
        self.assertEqual(set(result['scenarios']['candidate']),{'8','68'})
        self.assertIsNone(store.active())


if __name__ == '__main__':
    unittest.main()
