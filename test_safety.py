import copy
from datetime import timedelta
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from engine import advance_trade
from market import Bar, DataError
from safety_monitor import evaluate_warning, monitor
from storage import Store
from transport import Delivery, dispatch
from test_bot import NOW, active_trade


def bars_for(closes,minutes=1):
    start=NOW.replace(second=0)-timedelta(minutes=len(closes)*minutes)
    bars=[]
    for i,c in enumerate(closes):
        o=closes[i-1] if i else c
        bars.append(Bar(start+timedelta(minutes=i*minutes),o,max(o,c)+.2,min(o,c)-.2,c,minutes))
    return bars


class ProtectionTests(unittest.TestCase):
    def trade(self,side='BUY'):
        t=active_trade(side); t.update(protection_rule='staged-v1',protection_since=t['announced'])
        return t

    def bar(self,c,offset=0,low=None,high=None):
        return Bar(NOW.replace(second=0)+timedelta(minutes=offset),100,
                   high if high is not None else max(100,c)+.1,
                   low if low is not None else min(100,c)-.1,c)

    def test_half_and_full_risk_symmetric(self):
        for side,direction in [('BUY',1),('SELL',-1)]:
            t=self.trade(side)
            half,events=advance_trade(t,[self.bar(100+direction*5)])
            self.assertEqual(half['stop'],100-direction*5)
            self.assertEqual(events[0]['kind'],'protect')
            full,_=advance_trade(t,[self.bar(100+direction*10)])
            self.assertEqual(full['stop'],100)

    def test_stop_first_and_no_intrabar_retroactive_exit(self):
        t=self.trade()
        stopped,_=advance_trade(t,[self.bar(106,low=89)])
        self.assertEqual(stopped['status'],'closed'); self.assertEqual(stopped['stop'],90)
        # Low was below the newly proposed stop, but proposal exists only at close.
        live,events=advance_trade(t,[self.bar(106,low=92)])
        self.assertEqual(live['status'],'active'); self.assertEqual(live['stop'],95)
        self.assertFalse(any(e['kind']=='exit' for e in events))

    def test_wick_alone_does_not_ratchet(self):
        t,_=advance_trade(self.trade(),[self.bar(102,high=112)])
        self.assertEqual(t['stop'],90)

    def test_stop_never_loosened(self):
        for side,direction in [('BUY',1),('SELL',-1)]:
            t=self.trade(side); t['stop']=100+direction*2
            b=self.bar(100+direction*6,low=103 if direction==1 else 92,
                       high=108 if direction==1 else 97)
            b=Bar(b.start,104 if direction==1 else 96,b.high,b.low,b.close)
            changed,_=advance_trade(t,[b]); self.assertEqual(changed['stop'],t['stop'])

    def test_migration_does_not_ratchet_old_bars(self):
        t=self.trade(); t['protection_since']=NOW.timestamp()+900
        changed,_=advance_trade(t,[self.bar(106)])
        self.assertEqual(changed['stop'],90)

    def test_confirmed_pivot_trails_after_tp1_buy_and_sell(self):
        for side,direction in [('BUY',1),('SELL',-1)]:
            t=self.trade(side); t.update(tp1_hit=True,stop=100,tp2=150 if direction==1 else 50)
            lows=[110,108,111]; highs=[114,113,115]
            bars=[]
            for i in range(3):
                lo,hi=(lows[i],highs[i]) if direction==1 else (200-highs[i],200-lows[i])
                bars.append(Bar(NOW.replace(second=0)+timedelta(minutes=i*5),
                                (lo+hi)/2,hi,lo,(lo+hi)/2))
            changed,events=advance_trade(t,bars)
            self.assertEqual(changed['stop'],107 if direction==1 else 93)
            self.assertTrue(any(e['kind']=='protect' for e in events))

    def test_legacy_research_lifecycle_unchanged(self):
        changed,_=advance_trade(active_trade(),[self.bar(106)])
        self.assertEqual(changed['stop'],90)


class SafetyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'db'; self.store=Store(self.path); self.addCleanup(self.store.close)
        self.trade=active_trade(); self.trade['announced']=(NOW-timedelta(hours=1)).timestamp()
        self.store.save_transition(self.trade,[],NOW.timestamp())

    def test_correction_dedup_and_escalation(self):
        bars=bars_for([100+i*.1 for i in range(21)]+[101.1])
        event,state=evaluate_warning(self.trade,bars,NOW,{'peak':102.1})
        self.assertEqual(event['kind'],'correction')
        self.assertIsNone(evaluate_warning(self.trade,bars,NOW,state)[0])
        down=bars_for([110-i for i in range(22)])
        event,_=evaluate_warning(self.trade,down,NOW,{'level':1,'peak':111})
        self.assertEqual(event['kind'],'stop')

    def test_reversal_and_mirror(self):
        for side,direction in [('BUY',1),('SELL',-1)]:
            t=dict(self.trade,side=side,stop=50 if direction==1 else 150)
            bars=bars_for([100-direction*i*.4 for i in range(22)])
            event,_=evaluate_warning(t,bars,NOW)
            self.assertEqual(event['kind'],'reversal')

    def test_stale_gap_and_preentry_never_trigger(self):
        bars=bars_for([100-i*.4 for i in range(22)])
        with self.assertRaises(DataError): evaluate_warning(self.trade,bars,NOW+timedelta(minutes=2))
        with self.assertRaises(DataError): evaluate_warning(self.trade,bars[:-3]+bars[-2:],NOW)
        self.trade['announced']=NOW.timestamp()
        self.assertIsNone(evaluate_warning(self.trade,bars,NOW)[0])

    def test_standalone_dispatch_without_regular_cycle(self):
        bars=bars_for([110-i for i in range(22)])
        original=copy.deepcopy(self.store.active())
        monitor(self.store,bars,NOW); monitor(self.store,bars,NOW)
        self.assertEqual(self.store.active(),original)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox").fetchone()[0],1)
        telegram=Mock(); telegram.send.return_value=Delivery('sent',44)
        dispatch(self.store,telegram,NOW.timestamp(),only_kind='emergency')
        telegram.send.assert_called_once()
        self.assertNotIn('reply_to_message_id',telegram.send.call_args.kwargs)

    def test_closed_trade_pending_warning_is_dropped(self):
        monitor(self.store,bars_for([110-i for i in range(22)]),NOW)
        t=self.store.active(); t.update(status='closed',closed=NOW.timestamp())
        self.store.save_transition(t,[],NOW.timestamp())
        telegram=Mock(); dispatch(self.store,telegram,NOW.timestamp(),only_kind='emergency')
        telegram.send.assert_not_called()

    def test_emergency_claim_does_not_claim_entry(self):
        self.store.enqueue('unrelated','entry','message',NOW.timestamp())
        self.assertIsNone(self.store.claim(NOW.timestamp(),only_kind='emergency'))

    def test_two_dispatchers_claim_once(self):
        self.store.enqueue('one','emergency','message',NOW.timestamp())
        barrier=threading.Barrier(2); rows=[]; errors=[]
        def claim():
            db=Store(self.path)
            try:
                barrier.wait(); rows.append(db.claim(NOW.timestamp()))
            except Exception as exc: errors.append(exc)
            finally: db.close()
        threads=[threading.Thread(target=claim) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]); self.assertEqual(sum(r is not None for r in rows),1)


if __name__=='__main__': unittest.main()
