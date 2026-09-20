import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from bot import App
from market import DataError, Market, parse_quote, require_fresh
from storage import Store
from timing import DecisionClock
from transport import Delivery, dispatch
from test_bot import NOW, history, active_trade, response


class PriceGuardTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'db'); self.addCleanup(self.store.close)
        self.elapsed=[0.0]
        self.clock=DecisionClock(NOW,lambda:self.elapsed[0])
        self.market=Mock()
        self.market.fetch.return_value=history()
        self.market.quote.return_value={'price':100.2,'time':NOW.timestamp(),'source':'Twelve Data'}
        self.news=Mock(); self.news.check.return_value=(True,'clear',[])
        self.telegram=Mock(); self.telegram.send.return_value=Delivery('sent',42)
        self.d={'side':'BUY','price':100.,'sl':94.4,'tp1':107.2,'tp2':110.4,
                'atr':4.,'bar':NOW.isoformat(),'price_time':history()[-1].end.isoformat(),
                'buy':6,'sell':1,'checks':{'BUY':[True]*6+[False],'SELL':[False]*7}}

    def cycle(self):
        with patch('bot.analyze',return_value=self.d), patch.object(App,'quick_v4_update'):
            App(self.store,self.market,self.telegram,self.news,0).cycle(NOW,self.clock)

    def send(self):
        dispatch(self.store,self.telegram,now=lambda:self.clock.now().timestamp(),market=self.market)

    def test_strict_age_not_silently_relaxed(self):
        with self.assertRaises(DataError): require_fresh(history(),NOW+timedelta(seconds=106),120)
        require_fresh(history(),NOW+timedelta(seconds=106),600)

    def test_quote_rejects_stale_future_invalid_and_wrong_symbol(self):
        base={'symbol':'XAU/USD','rate':4328.41,'timestamp':NOW.timestamp()}
        self.assertEqual(parse_quote(base,NOW)['price'],4328.41)
        for change in ({'timestamp':NOW.timestamp()-91},{'timestamp':NOW.timestamp()+1},
                       {'rate':'nan'},{'rate':0},{'symbol':'EUR/USD'},{'timestamp':None}):
            with self.subTest(change=change),self.assertRaises(DataError):
                parse_quote(dict(base,**change),NOW)

    def test_quote_checks_time_after_network(self):
        session=Mock(); session.get.return_value=response({'symbol':'XAU/USD','rate':100,'timestamp':NOW.timestamp()})
        with self.assertRaises(DataError):
            Market('dummy',session).quote(lambda:NOW+timedelta(seconds=91))

    def test_entry_uses_quote_and_preserves_level_distances(self):
        self.cycle(); t=self.store.active()
        self.assertAlmostEqual(t['entry'],100.2)
        self.assertAlmostEqual(t['entry']-t['stop'],5.6)
        self.assertAlmostEqual(t['tp1']-t['entry'],7.2)
        self.send(); self.assertEqual(self.store.active()['status'],'active')
        self.assertEqual(self.market.quote.call_count,2)
        body=self.telegram.send.call_args.args[0]
        self.assertIn('100.20',body); self.assertIn('JustMarkets',body)

    def test_sell_reanchoring_preserves_level_order(self):
        self.d.update(side='SELL',sl=105.6,tp1=92.8,tp2=89.6)
        self.cycle(); t=self.store.active()
        self.assertGreater(t['stop'],t['entry']); self.assertLess(t['tp2'],t['tp1'])
        self.assertAlmostEqual(t['tp1'],93.0)

    def test_moved_or_unavailable_quote_blocks_entry(self):
        self.market.quote.return_value['price']=102
        self.cycle(); self.assertIsNone(self.store.active())
        self.assertEqual(self.store.get('last_error'),'market_price_moved')

    def test_unavailable_quote_with_divergent_candle_blocks_entry(self):
        self.market.quote.side_effect=DataError('market_quote_unavailable')
        self.cycle(); self.assertIsNone(self.store.active())

    def test_slow_news_blocks_entry(self):
        def news(*a): self.elapsed[0]=166; return True,'clear',[]
        self.news.check.side_effect=news
        self.cycle(); self.assertIsNone(self.store.active()); self.market.quote.assert_not_called()

    def test_slow_quote_blocks_entry(self):
        def quote(*a):
            self.elapsed[0]=166
            return {'price':100.,'time':self.clock.now().timestamp(),'source':'Twelve Data'}
        self.market.quote.side_effect=quote
        self.cycle(); self.assertIsNone(self.store.active())

    def test_expired_quote_not_queued_even_with_current_candles(self):
        self.elapsed[0]=91
        self.cycle()
        self.assertIsNone(self.store.active())
        self.assertEqual(self.store.get('last_error'),'market_quote_stale')

    def test_future_quote_not_queued(self):
        self.market.quote.return_value['time']=NOW.timestamp()+1
        self.cycle()
        self.assertIsNone(self.store.active())

    def test_price_move_during_queue_never_sends_entry(self):
        self.cycle(); self.market.quote.return_value['price']=103
        self.send(); self.telegram.send.assert_not_called(); self.assertIsNone(self.store.active())

    def test_queue_expiry_and_retry_do_not_revive_entry(self):
        self.cycle(); self.telegram.send.return_value=Delivery('retry',retry_after=120)
        self.send(); self.elapsed[0]=121; self.send()
        self.assertEqual(self.telegram.send.call_count,1); self.assertIsNone(self.store.active())

    def test_legacy_pending_entry_without_quote_is_rejected(self):
        t=active_trade(); t.update(status='pending',announced=None)
        self.store.prepare_entry(t,'old entry',NOW.timestamp())
        self.send(); self.telegram.send.assert_not_called(); self.assertIsNone(self.store.active())

    def test_active_followups_still_send_without_quote(self):
        self.store.enqueue('follow-test','follow','monitoring',NOW.timestamp())
        self.send(); self.telegram.send.assert_called_once_with('monitoring')
        self.market.quote.assert_not_called()


if __name__=='__main__': unittest.main()
