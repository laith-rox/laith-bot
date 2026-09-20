import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
from datetime import timedelta
from storage import Store
from bot import App, run
from test_bot import NOW
from test_safety import bars_for
from fast import MinuteMarket, _MINUTE_CACHE, _MINUTE_BACKOFF
from market import DataError

class RuntimeRepairs(unittest.TestCase):
    def test_only_owner_can_bind_emergency_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'db')
            try:
                tg=Mock(chat_id='123')
                app=App(s,Mock(),tg,Mock())
                for sender,expected in [('999',None),('123','-55')]:
                    tg.read.return_value=[{'update_id':1,'message':{'chat':{'id':-55,'type':'supergroup'},'from':{'id':sender},'text':'/emergencyhere'}}]
                    app.commands(NOW)
                    self.assertEqual(s.get('emergency_chat_id'),expected)
                tg.send_to.assert_called_once()
            finally:s.close()

    def test_poll_failure_does_not_skip_market_cycle(self):
        app=Mock();app.commands.side_effect=RuntimeError('telegram_read_failed')
        args=SimpleNamespace(db='unused',telegram_token='test',telegram_chat='123',twelve_key='test',cooldown=60,interval=1)
        with patch('bot.Store'),patch('bot.Telegram'),patch('bot.Market'),patch('bot.NewsGuard'),patch('bot.start_worker'),patch('bot.start_safety_worker'),patch('bot.App',return_value=app),patch('bot.dispatch') as delivery,patch('bot.time.sleep',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):run(args)
            app.cycle.assert_called_once();delivery.assert_called_once()

    def test_minute_cache_and_quota_backoff_shared(self):
        _MINUTE_CACHE.clear();_MINUTE_BACKOFF.clear()
        a,b=MinuteMarket('test'),MinuteMarket('test')
        bars=bars_for([100]*600)
        with patch.object(a,'_fetch',return_value=bars) as first,patch.object(b,'_fetch') as second:
            self.assertEqual(len(a.fetch(NOW,size=60)),60)
            self.assertEqual(len(b.fetch(NOW,size=600)),600)
            first.assert_called_once();second.assert_not_called()
        _MINUTE_CACHE.clear()
        with patch.object(a,'_fetch',side_effect=DataError('minute_quota_reached')),patch.object(b,'_fetch') as second:
            with self.assertRaises(DataError):a.fetch(NOW)
            with self.assertRaises(DataError):b.fetch(NOW)
            second.assert_not_called()
        _MINUTE_CACHE.clear();_MINUTE_BACKOFF.clear()

if __name__=='__main__':unittest.main()
