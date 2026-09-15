"""Notification routing and truthful labels; all network traffic is mocked."""
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import requests

from bot import App
from engine import make_trade
from market import DataError
from messages import entry, emergency, fully_qualified, transition
from reports import snapshot, report_message
from storage import Store
from transport import Telegram, dispatch
from test_bot import NOW, history, active_trade, response


def decision(side='BUY', when=NOW, forced=False):
    direction = 1 if side == 'BUY' else -1
    return {'side': side, 'price': 100., 'atr': 2.,
            'sl': 100-10*direction, 'tp1': 100+18*direction, 'tp2': 100+26*direction,
            'buy': 7 if side == 'BUY' else 1, 'sell': 7 if side == 'SELL' else 1,
            'checks': {'BUY': [side == 'BUY']*7, 'SELL': [side == 'SELL']*7},
            'bar': when.isoformat(), 'price_time': when.replace(second=0).isoformat(),
            'forced': forced, 'reason': 'best_available_bias' if forced else 'entry_conditions_met'}


class MessageFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'state.sqlite3'
        self.store = Store(self.path)
        self.session = Mock()
        self.counter = 40
        def post(*args, **kwargs):
            self.counter += 1
            return response({'ok': True, 'result': {'message_id': self.counter, 'chat': {'id': 1}}})
        self.session.post.side_effect = post
        self.telegram = Telegram('offline', '1', self.session)
        self.market, self.news = Mock(), Mock()
        self.news.check.return_value = True, 'calendar_clear', []
        self.app = App(self.store, self.market, self.telegram, self.news)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def delivered_entry(self):
        d = decision()
        trade = make_trade(d, NOW)
        self.store.prepare_entry(trade, entry(trade, d), NOW.timestamp())
        dispatch(self.store, self.telegram, NOW.timestamp())
        return self.store.active()

    def pending_rows(self):
        return [dict(row) for row in self.store.db.execute("SELECT * FROM outbox WHERE status='pending'")]

    def restart(self):
        self.store.close()
        self.store = Store(self.path)
        self.app.store = self.store

    def test_new_entry_replaces_report_in_same_cycle_without_duplicate_delivery(self):
        self.market.fetch.return_value = history()
        self.app.cycle(NOW)
        self.assertEqual([r['kind'] for r in self.pending_rows()], ['entry'])
        dispatch(self.store, self.telegram, NOW.timestamp()+1)
        self.restart()
        self.app.cycle(NOW+timedelta(seconds=2))
        dispatch(self.store, self.telegram, NOW.timestamp()+2)
        self.assertEqual(self.session.post.call_count, 1)
        self.assertEqual(self.store.active()['status'], 'active')

    def test_active_trade_gets_one_follow_per_slot_including_quarter_hour(self):
        trade = self.delivered_entry()
        for minutes in (5, 5, 10, 15, 15):
            when = NOW+timedelta(minutes=minutes)
            self.app.periodic_reports(decision(when=when), [], when, 'active_signal')
            dispatch(self.store, self.telegram, when.timestamp())
            self.restart()
        posts = self.session.post.call_args_list
        self.assertEqual(len(posts), 4)
        for post in posts[1:]:
            payload = post.kwargs['json']
            self.assertEqual(payload['reply_parameters'], {'message_id': trade['message_id'],
                                                           'allow_sending_without_reply': True})
            self.assertIn(trade['id'], payload['text'])
            self.assertNotIn('report-', payload['text'])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE kind='report'").fetchone()[0], 0)

    def test_report_cadence_and_replies_when_no_active_signal(self):
        for minutes in (0, 5, 10, 15):
            when = NOW+timedelta(minutes=minutes)
            self.app.periodic_reports(decision(when=when), [], when, 'cooldown')
            dispatch(self.store, self.telegram, when.timestamp())
        posts = [call.kwargs['json'] for call in self.session.post.call_args_list]
        self.assertEqual(len(posts), 4)
        self.assertNotIn('reply_parameters', posts[0])
        self.assertEqual(posts[1]['reply_parameters']['message_id'], 41)
        self.assertEqual(posts[2]['reply_parameters']['message_id'], 41)
        self.assertNotIn('reply_parameters', posts[3])
        self.assertIsNone(self.store.active())

    def test_emergency_supersedes_routine_but_later_followup_resumes(self):
        trade = self.delivered_entry()
        when = NOW+timedelta(minutes=5)
        self.app.periodic_reports(decision(when=when), [], when)
        opposite = decision('SELL', when, forced=True)
        self.app.monitor_reversal(trade, opposite, when.timestamp())
        self.app.periodic_reports(opposite, [], when)
        self.assertEqual([r['kind'] for r in self.pending_rows()], ['emergency'])
        dispatch(self.store, self.telegram, when.timestamp())
        self.assertEqual(self.session.post.call_args.kwargs['json']['reply_parameters']['message_id'], 41)
        self.restart()
        when += timedelta(minutes=5)
        self.app.monitor_reversal(trade, decision('SELL', when, forced=True), when.timestamp())
        self.app.periodic_reports(decision('SELL', when, forced=True), [], when)
        self.assertEqual([r['kind'] for r in self.pending_rows()], ['follow'])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE kind='emergency'").fetchone()[0], 1)

    def test_milestone_keeps_priority_and_replaces_unsent_routine_only(self):
        trade = self.delivered_entry()
        when = NOW+timedelta(minutes=5)
        self.app.periodic_reports(decision(when=when), [], when)
        trade.update(tp1_hit=True, stop=trade['entry'])
        self.store.save_transition(trade, [('tp1', transition(trade, 'tp1'))], when.timestamp())
        self.store.enqueue('owner-command', 'command', 'status', when.timestamp())
        self.app.periodic_reports(decision(when=when), [], when)
        dispatch(self.store, self.telegram, when.timestamp())
        posts = [c.kwargs['json'] for c in self.session.post.call_args_list]
        self.assertEqual(len(posts), 3)
        self.assertIn('الهدف الأول', posts[1]['text'])
        self.assertEqual(posts[1]['reply_parameters']['message_id'], 41)
        self.assertEqual(posts[2]['text'], 'status')
        self.assertTrue(self.store.active()['tp1_hit'])

    def test_exit_before_new_entry_and_each_reply_uses_its_own_parent(self):
        old = self.delivered_entry()
        when = NOW+timedelta(minutes=65)
        old.update(status='closed', outcome='STOP', closed=when.timestamp(), exit=90., r=-1.)
        self.store.save_transition(old, [('exit', transition(old, 'exit'))], when.timestamp())
        new_d = decision('SELL', when)
        new = make_trade(new_d, when)
        new['id'] = '000-new-signal'  # Would sort before the old exit without event ordering.
        self.store.prepare_entry(new, entry(new, new_d), when.timestamp())
        self.app.periodic_reports(new_d, [], when)
        dispatch(self.store, self.telegram, when.timestamp())
        payloads = [c.kwargs['json'] for c in self.session.post.call_args_list]
        self.assertIn('انتهت متابعة', payloads[1]['text'])
        self.assertEqual(payloads[1]['reply_parameters']['message_id'], 41)
        self.assertIn('إشارة ذهب جديدة', payloads[2]['text'])
        self.assertNotIn('reply_parameters', payloads[2])
        when += timedelta(minutes=5)
        self.app.periodic_reports(decision('SELL', when), [], when)
        dispatch(self.store, self.telegram, when.timestamp())
        self.assertEqual(self.session.post.call_args.kwargs['json']['reply_parameters']['message_id'], 43)

    def test_uncertain_entry_keeps_monitoring_without_inventing_reply_id(self):
        self.session.post.side_effect = requests.ReadTimeout()
        self.delivered_entry()
        self.assertTrue(self.store.get('paused'))
        self.session.post.side_effect = None
        self.session.post.return_value = response({'ok': True, 'result': {'message_id': 50, 'chat': {'id': 1}}})
        when = NOW+timedelta(minutes=5)
        self.app.periodic_reports(decision(when=when), [], when, 'paused')
        dispatch(self.store, self.telegram, when.timestamp())
        payload = self.session.post.call_args.kwargs['json']
        self.assertNotIn('reply_parameters', payload)
        self.assertIn('وصول رسالة الدخول غير مؤكد', payload['text'])
        self.assertEqual(self.store.active()['status'], 'uncertain_delivery')

    def test_failed_entry_releases_report_without_orphan_trade_followup(self):
        self.session.post.side_effect = None
        self.session.post.return_value = response({'ok': False, 'error_code': 400}, 400)
        self.delivered_entry()
        self.app.periodic_reports(decision(), [], NOW)
        self.assertEqual([r['kind'] for r in self.pending_rows()], ['report'])
        self.assertIsNone(self.store.active())

    def test_data_failure_updates_existing_trade_without_reusing_old_quote(self):
        trade = self.delivered_entry()
        self.market.fetch.side_effect = DataError('market_connection_failed')
        when = NOW+timedelta(minutes=5)
        self.app.cycle(when)
        dispatch(self.store, self.telegram, when.timestamp()+1)
        payload = self.session.post.call_args.kwargs['json']
        self.assertEqual(payload['reply_parameters']['message_id'], 41)
        self.assertIn('تعذّر تحديث', payload['text'])
        self.assertNotIn('آخر إغلاق 5د:', payload['text'])
        self.assertEqual(self.store.active()['id'], trade['id'])

    def test_retry_preserves_thread_and_does_not_duplicate_success(self):
        self.delivered_entry()
        when = NOW+timedelta(minutes=5)
        self.app.periodic_reports(decision(when=when), [], when)
        self.session.post.side_effect = [response({'ok': False, 'error_code': 429,
                                                  'parameters': {'retry_after': 10}}, 429),
                                       response({'ok': True, 'result': {'message_id': 42, 'chat': {'id': 1}}})]
        dispatch(self.store, self.telegram, when.timestamp())
        dispatch(self.store, self.telegram, when.timestamp()+9)
        dispatch(self.store, self.telegram, when.timestamp()+10)
        dispatch(self.store, self.telegram, when.timestamp()+20)
        self.assertEqual(self.session.post.call_count, 3)
        for call in self.session.post.call_args_list[1:]:
            self.assertEqual(call.kwargs['json']['reply_parameters']['message_id'], 41)

    def test_no_late_report_reply_after_entry_supersedes_market_summary(self):
        self.app.periodic_reports(decision(), [], NOW)
        self.delivered_entry()
        self.app.periodic_reports(decision(), [], NOW)
        dispatch(self.store, self.telegram, NOW.timestamp())
        self.assertEqual(self.session.post.call_count, 1)
        self.assertIsNone(self.store.get('current_report'))


class MessageMeaningTests(unittest.TestCase):
    def test_forced_majority_never_claims_full_conditions_or_medium_risk(self):
        d = decision(forced=True)
        trade = make_trade(d, NOW)
        report = snapshot(d, NOW)
        self.assertFalse(fully_qualified(d, 'BUY'))
        self.assertFalse(report['qualified'])
        self.assertIn('مرتفع', report['risk'])
        for text in (entry(trade, d), report_message(report, d),
                     emergency(active_trade('SELL'), d, 'urgent')):
            self.assertNotIn('اكتملت شروط', text)
            self.assertNotIn('مستوفية شروط الدخول', text)

    def test_strict_six_conditions_uses_actual_core_gate_and_no_guarantee(self):
        d = decision()
        d['checks']['BUY'][2] = False
        d['buy'] = 6
        self.assertTrue(fully_qualified(d, 'BUY'))
        self.assertIn('مستوفية شروط الدخول — غير مضمونة', entry(make_trade(d, NOW), d))
        d['checks']['BUY'][2] = True
        d['checks']['BUY'][3] = False
        self.assertFalse(fully_qualified(d, 'BUY'))

    def test_ambiguous_close_has_no_fabricated_exit_or_profit(self):
        trade = active_trade()
        trade.update(status='closed', outcome='AMBIGUOUS', closed=NOW.timestamp(), exit=None, r=None)
        text = transition(trade, 'exit')
        self.assertIn('غير محسوم', text)
        self.assertNotIn('سعر نهاية المتابعة:', text)
        self.assertNotIn('+0.00R', text)

    def test_reference_and_untrusted_block_reason_are_html_escaped(self):
        d = decision()
        trade = make_trade(d, NOW)
        trade['id'] = '<new&signal>'
        self.assertIn('&lt;new&amp;signal&gt;', entry(trade, d))
        text = report_message(snapshot(d, NOW, '<reason&>'), d)
        self.assertIn('&lt;reason&amp;&gt;', text)


if __name__ == '__main__':
    unittest.main()
