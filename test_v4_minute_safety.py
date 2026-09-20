import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import Mock
from market import DataError
from storage import Store
from transport import Delivery
from test_bot import NOW, active_trade
from test_safety import bars_for
from v4_minute_safety import monitor, flush

class MinuteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'db');self.addCleanup(self.store.close)
        self.store.db.execute('CREATE TABLE v4_quick_paper(id TEXT PRIMARY KEY,data TEXT)')
        self.t=active_trade(); self.t.update(id='v4:test',announced=(NOW-timedelta(seconds=90)).timestamp())
        self.store.set('v4_active',self.t)

    def test_first_minutes_stop_warning_durable_and_deduplicated(self):
        bars=bars_for([100]*21+[89])
        monitor(self.store,bars,NOW);monitor(self.store,bars,NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
        self.assertEqual(self.store.get('v4_active'),self.t)
        telegram=Mock();telegram.send.return_value=Delivery('sent',123)
        flush(self.store,telegram,NOW.timestamp())
        telegram.send.assert_called_once()
        self.assertIn('تجاوز الوقف',telegram.send.call_args.args[0])
        self.assertEqual(self.store.db.execute('SELECT status FROM outbox').fetchone()[0],'sent')

    def test_closed_trade_drops_pending_alert(self):
        monitor(self.store,bars_for([100]*21+[89]),NOW)
        self.store.set('v4_active',None)
        telegram=Mock();flush(self.store,telegram,NOW.timestamp())
        telegram.send.assert_not_called()

    def test_stale_bars_cannot_warn(self):
        with self.assertRaises(DataError):monitor(self.store,bars_for([100]*21+[89]),NOW+timedelta(minutes=5))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_quick_sell_monitored_before_four_minutes(self):
        self.store.set('v4_active',None)
        t=dict(self.t,side='SELL',stop=110)
        with self.store.db:self.store.db.execute('INSERT INTO v4_quick_paper VALUES (?,?)',(t['id'],json.dumps(t)))
        monitor(self.store,bars_for([100]*21+[111]),NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)

if __name__=='__main__': unittest.main()
