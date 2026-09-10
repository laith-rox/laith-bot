"""Regression checks for decision causality, fair paper comparisons and entry safety."""
from datetime import timedelta
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from market import Bar, DataError
from engine import make_trade
from fast import paper_fill, aggregate_five, advance_fast
from fast_candidate import analyze_candidate, confirmed_swings, structure, RULE
from fast_research import cost_summary, simulate_fast
from fast_service import paper_cycle, cycle_rule, fast_status
from fast_compare import compare_saved
from news import week_start
from storage import Store
from test_fast import minutes, AT, fixture_decision


class CandidateTests(unittest.TestCase):
    def store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Store(Path(tmp.name)/'db')
        self.addCleanup(store.close)
        store.db.executescript('CREATE TABLE fast_paper(id TEXT PRIMARY KEY,data TEXT NOT NULL);'
                              'CREATE TABLE fast2_paper(id TEXT PRIMARY KEY,data TEXT NOT NULL);'
                              'CREATE TABLE fast_bars(time REAL PRIMARY KEY,open REAL,high REAL,low REAL,close REAL);')
        return store

    def test_retest_entry_is_symmetric_and_risk_bounded(self):
        for rev, side in ((False,'BUY'),(True,'SELL')):
            d = analyze_candidate(minutes(reverse=rev),AT)
            self.assertEqual(d['side'],side)
            self.assertEqual(d['rule'],RULE)
            self.assertLessEqual(abs(d['price']-d['sl']),3.5)
            self.assertEqual(abs(d['tp2']-d['price']),5)

    def test_minute_dip_is_not_a_sell_reversal_in_five_minute_uptrend(self):
        bars = minutes()
        p = bars[-9].close
        for i in range(-8,0):
            c = p-.05
            bars[i] = Bar(bars[i].start,p,p+.04,c-.04,c,1)
            p = c
        d = analyze_candidate(bars,AT)
        self.assertEqual(d['context']['bias'],'BUY')
        self.assertEqual(d['side'],'WAIT')

    def test_unconfirmed_swing_cannot_be_used_before_right_candles_close(self):
        start = AT-timedelta(minutes=30)
        highs = [101,102,106,103,102]
        bars = [Bar(start+timedelta(minutes=5*i),100,h,99,100,5) for i,h in enumerate(highs)]
        self.assertEqual(confirmed_swings(bars[:-1])[0],[])
        self.assertEqual(confirmed_swings(bars)[0],[(2,106)])

    def test_confirmed_structure_break_can_turn_before_ema_alignment(self):
        fives = aggregate_five(minutes(reverse=True))
        p = max(b.high for b in fives[-8:-2])+2
        for i in (-2,-1):
            b = fives[i]
            fives[i] = Bar(b.start,p-.1,p+.1,p-.2,p,5)
        d = structure(fives)
        self.assertEqual(d['bias'],'BUY')
        self.assertEqual(d['phase'],'confirmed_break')

    def test_wide_pullback_is_rejected_instead_of_squeezing_stop(self):
        bars = minutes()
        b = bars[-2]
        bars[-2] = Bar(b.start,b.open,b.high,b.close-5,b.close,1)
        with patch('fast_candidate.structure',return_value={'bias':'BUY','phase':'trend','level':100}):
            d = analyze_candidate(bars,AT)
        self.assertEqual(d['side'],'WAIT')
        self.assertEqual(d['reason'],'candidate_structural_stop_too_wide')

    def test_fill_rechecks_actual_risk_and_preserves_setup(self):
        d = dict(fixture_decision(minutes(),AT),rule=RULE,reason='retest',max_fill_risk=3.5)
        d['sl'] = d['price']-3.4
        p = d['price']+.3
        self.assertIsNone(paper_fill(d,Bar(AT,p,p+.1,p-.1,p,1)))
        p = d['price']
        t = paper_fill(d,Bar(AT,p,p+.1,p-.1,p,1))
        self.assertEqual(t['rule'],RULE)
        self.assertEqual(t['setup'],'retest')

    def test_one_price_request_feeds_both_independent_paper_rules(self):
        store = self.store()
        data = minutes()
        market, news = Mock(), Mock()
        market.fetch.return_value = data
        news.check.return_value = (True,'clear',[])
        d = fixture_decision(data,AT)
        t = make_trade(d,AT-timedelta(minutes=5))
        t.update(status='active',announced=(AT-timedelta(minutes=5)).timestamp())
        store.set('fast_paper_watch',t)
        paper_cycle(store,market,news,AT)
        market.fetch.assert_called_once()
        self.assertEqual(store.get('fast_paper_watch')['id'],t['id'])
        self.assertIsNotNone(store.get('fast2_paper_pending'))
        self.assertIsNone(store.active())

    def test_expired_pending_cannot_fill_from_old_prices_after_outage(self):
        store = self.store()
        data = minutes()
        stamp = (AT-timedelta(minutes=8)).timestamp()
        store.set('fast2_paper_pending',{'time':stamp,'decision':fixture_decision(data,AT)})
        with patch('fast_service.paper_fill') as fill:
            cycle_rule(store,data,AT,True,[],'fast2',lambda b,n:{'side':'WAIT','bar':b[-1].end.isoformat()})
        fill.assert_not_called()
        self.assertIsNone(store.get('fast2_paper_pending'))

    def test_fee_scenarios_count_protected_stop_as_net_loss(self):
        trades = [{'r':0.,'entry':100.,'initial_sl':98.},
                  {'r':1.,'entry':100.,'initial_sl':98.},
                  {'r':None,'entry':100.,'initial_sl':98.}]
        s = cost_summary(trades,[.5])[0]
        self.assertEqual((s['measured'],s['wins'],s['losses']),(2,1,1))
        self.assertAlmostEqual(s['net_r'],.5)

    def test_missing_first_minute_invalidates_paper_result(self):
        d = fixture_decision(minutes(),AT)
        p = d['price']
        t = paper_fill(d,Bar(AT,p,p+.1,p-.1,p,1))
        result = advance_fast(t,[Bar(AT+timedelta(minutes=1),p,p+6,p-.1,p+5,1)])
        self.assertTrue(result['data_gap'])
        self.assertIsNone(result['r'])

    def test_time_exit_without_intervening_prices_is_not_measured_as_profit(self):
        d = fixture_decision(minutes(),AT)
        p = d['price']
        t = paper_fill(d,Bar(AT,p,p+.1,p-.1,p,1))
        result = advance_fast(t,[Bar(AT+timedelta(minutes=20),p+2,p+2.1,p+1.9,p+2,1)])
        self.assertEqual(result['outcome'],'TIME_LIMIT')
        self.assertTrue(result['data_gap'])
        self.assertIsNone(result['r'])

    def test_research_expired_signal_is_not_filled_across_a_gap(self):
        data = minutes()
        data = data[:301]+[Bar(b.start+timedelta(minutes=5),b.open,b.high,b.low,b.close,1) for b in data[301:]]
        decisions = [fixture_decision(data[:300],AT)]
        def decide(b,n):
            return decisions.pop() if decisions else {'side':'WAIT'}
        with patch('fast_research.fast_window',return_value=True),patch('fast_research.paper_fill') as fill:
            simulate_fast(data,[.5],[],analyzer=decide)
        fill.assert_not_called()

    def test_saved_comparison_is_labelled_development_and_readable_without_orders(self):
        store = self.store()
        bars = minutes()
        with store.db:
            store.db.executemany('INSERT INTO fast_bars VALUES (?,?,?,?,?)',
                                 [(b.start.timestamp(),b.open,b.high,b.low,b.close) for b in bars])
        store.set('calendar',{'week':week_start(AT).isoformat(),'events':[],'fetched':AT.timestamp()})
        compare_saved(store,AT)
        result = store.get('fast_comparison')
        self.assertEqual(result['mode'],'DEVELOPMENT_COMPARISON_NOT_HOLDOUT')
        self.assertEqual(result['decision'],'PAPER_COMPARISON_ONLY_NO_AUTOMATIC_ACTIVATION')
        self.assertIsNone(store.active())
        self.assertIn('إعادة الاختبار',fast_status(store))
        self.assertLess(len(fast_status(store)),4096)


if __name__ == '__main__':
    unittest.main()
