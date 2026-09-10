from datetime import timedelta
import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from test_bot import NOW, response
from market import Bar, DataError
from fast import (MinuteMarket, analyze_fast, aggregate_five, advance_fast,
                  fast_window, paper_fill, MAX_HOLD)
from fast_research import simulate_fast, evaluate, COSTS
from fast_service import paper_cycle, finish_paper, fast_status
from storage import Store

AT = NOW.replace(hour=19)


def minutes(n=600, reverse=False):
    bars = []
    start = AT.replace(second=0)-timedelta(minutes=n)
    p = 100.
    for i in range(n):
        c = 100 + .02*i + (.08 if i%2 else -.08)
        bars.append(Bar(start+timedelta(minutes=i),p,max(p,c)+.12,min(p,c)-.12,c,1))
        p = c
    b = bars[-1]
    p = max(b.high for b in bars[-7:-1])+.15
    bars[-1] = Bar(b.start,b.open,p+.01,b.low,p,1)
    if reverse:
        bars = [Bar(b.start,300-b.open,300-b.low,300-b.high,300-b.close,1) for b in bars]
    return bars


def fixture_decision(bars,now):
    p=bars[-1].close
    return {'side':'BUY','price':p,'atr':2.,'sl':p-1.5,'tp1':p+3,'tp2':p+5,'bar':bars[-1].end.isoformat()}


class FastTests(unittest.TestCase):
    def test_long_short_breakout_and_bounded_risk(self):
        for reverse,side in ((False,'BUY'),(True,'SELL')):
            d=analyze_fast(minutes(reverse=reverse),AT)
            self.assertEqual(d['side'],side)
            self.assertAlmostEqual(abs(d['tp2']-d['price']),5)
            self.assertLessEqual(abs(d['price']-d['sl']),3.5)

    def test_gap_stale_and_wrong_interval_rejected(self):
        bars=minutes()
        for data,at in ((bars[:-5]+bars[-4:],AT),(bars,AT+timedelta(minutes=2)),
                        ([Bar(b.start,b.open,b.high,b.low,b.close,5) for b in bars],AT)):
            with self.assertRaises(DataError):
                analyze_fast(data,at)

    def test_aggregation_excludes_partial_clock_group(self):
        self.assertEqual(len(aggregate_five(minutes())),120)
        self.assertEqual(len(aggregate_five(minutes()[1:])),119)

    def test_fill_does_not_chase_or_cross_stop(self):
        bars=minutes()
        d=analyze_fast(bars,AT)
        b=bars[-1]
        self.assertIsNone(paper_fill(d,Bar(b.start,d['sl']-1,d['price'],d['sl']-2,d['sl'],1)))
        self.assertIsNone(paper_fill(d,Bar(b.start,d['price']+2,d['price']+3,d['price'],d['price']+2,1)))

    def trade(self):
        d=fixture_decision(minutes(),AT)
        b=Bar(AT.replace(second=0)+timedelta(minutes=1),d['price'],d['price']+.2,d['price']-.2,d['price'],1)
        return paper_fill(d,b)

    def test_holding_limit_is_known_before_exit(self):
        t=self.trade();p=t['entry']
        start=AT.replace(second=0)+timedelta(minutes=1)
        bars=[Bar(start+timedelta(minutes=i),p+.1*i,p+.1*i+.1,p+.1*i-.1,p+.1*i,1) for i in range(21)]
        result=advance_fast(t,bars)
        self.assertEqual(result['outcome'],'TIME_LIMIT')
        self.assertEqual(result['closed']-t['announced'],MAX_HOLD)
        self.assertAlmostEqual(result['exit'],p+2)

    def test_minute_gap_excludes_result_and_replay_idempotent(self):
        t=self.trade();p=t['entry']
        b=Bar(AT.replace(second=0)+timedelta(minutes=5),p,p+6,p-.1,p+5,1)
        result=advance_fast(t,[b])
        self.assertIsNone(result['r'])
        self.assertTrue(result['data_gap'])
        self.assertEqual(advance_fast(result,[b]),result)

    def test_minute_provider_params_and_sanitized_errors(self):
        session=Mock()
        b=minutes()[-1]
        payload={'meta':{'symbol':'XAU/USD'},'values':[{'datetime':b.start.isoformat(),'open':b.open,
                    'high':b.high,'low':b.low,'close':b.close}]}
        session.get.return_value=response(payload)
        result=MinuteMarket('private',session).fetch(AT)
        self.assertEqual(result[0].minutes,1)
        self.assertEqual(session.get.call_args.kwargs['params']['interval'],'1min')
        session.get.return_value=response({'status':'error','code':429,'message':'apikey=private'})
        with self.assertRaisesRegex(DataError,'minute_quota_reached'):
            MinuteMarket('private',session).fetch(AT)

    def test_time_window_and_weekend(self):
        self.assertTrue(fast_window(AT))
        self.assertFalse(fast_window(AT.replace(hour=16)))
        self.assertFalse(fast_window(AT.replace(hour=21)))
        self.assertFalse(fast_window(AT+timedelta(days=2)))

    def test_cost_sensitivity_and_holdout(self):
        with patch('fast_research.analyze_fast',side_effect=fixture_decision),patch('fast_research.fast_window',return_value=True):
            result=simulate_fast(minutes(),COSTS,[])
            future=simulate_fast(minutes(),COSTS,[],start_from=AT+timedelta(days=1))
        self.assertGreater(result['closed'],0)
        self.assertLessEqual(result['cost_scenarios'][-1]['net_r'],result['cost_scenarios'][0]['net_r'])
        self.assertEqual(future['signals'],0)
        self.assertEqual(future['closed'],0)

    def test_fill_occurs_after_decision_on_next_full_minute(self):
        decision_times=[];fill_times=[]
        def decide(bars,now):
            decision_times.append(now)
            return fixture_decision(bars,now)
        def fill(d,b):
            fill_times.append(b.start)
            return paper_fill(d,b)
        with patch('fast_research.analyze_fast',side_effect=decide),patch('fast_research.paper_fill',side_effect=fill),patch('fast_research.fast_window',return_value=True):
            simulate_fast(minutes(),COSTS,[])
        self.assertTrue(fill_times)
        self.assertGreater(fill_times[0],decision_times[0])
        self.assertEqual((fill_times[0]-decision_times[0]).total_seconds(),52)

    def test_news_blocks_entries_and_costs_finite(self):
        with patch('fast_research.analyze_fast',side_effect=fixture_decision):
            result=simulate_fast(minutes(),COSTS,[{'time':AT.timestamp()-15*60}],start_from=AT-timedelta(minutes=15))
        self.assertEqual(result['signals'],0)
        with self.assertRaises(ValueError):
            simulate_fast(minutes(),[float('nan')],[])

    def test_paper_state_is_separate_and_close_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db')
            store.db.execute('CREATE TABLE fast_paper(id TEXT PRIMARY KEY,data TEXT NOT NULL)')
            t=self.trade()
            t.update(status='closed',closed=AT.timestamp()+600,outcome='TIME_LIMIT',r=-1.)
            finish_paper(store,t);finish_paper(store,t)
            self.assertEqual(store.get('fast_paper_stats')['closed'],1)
            self.assertEqual(store.stats()['closed'],0)
            self.assertIn('لا إشارات دخول',fast_status(store))
            store.close()


if __name__=='__main__':
    unittest.main()
