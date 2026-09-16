import copy
import unittest
from messages import signal_assessment, entry
from reports import trade_follow_message, report_message, snapshot
from test_bot import NOW, active_trade


class StrengthTests(unittest.TestCase):
    def decision(self, side='BUY'):
        other='SELL' if side=='BUY' else 'BUY'
        return {'side':side,'checks':{side:[True]*7,other:[False]*7},
                'buy':7 if side=='BUY' else 0,'sell':7 if side=='SELL' else 0,
                'context':{'trend':side,'local_structure':side,'phase':'aligned',
                           'entry_allowed':True,'support':90,'resistance':110},
                'price':100.,'atr':4.,'price_time':NOW.isoformat(),
                'forced':False,'reason':'entry_conditions_met'}

    def test_strong_is_symmetric_and_requires_structure(self):
        for side in ('BUY','SELL'):
            d=self.decision(side)
            self.assertEqual(signal_assessment(d,side)[0],'قوية')
            d['context']['local_structure']='WAIT'
            self.assertEqual(signal_assessment(d,side)[0],'متوسطة')

    def test_high_score_cannot_hide_context_or_rsi_failure(self):
        for phase in ('pullback','conflict','trend_break'):
            d=self.decision(); d['context']['phase']=phase
            self.assertEqual(signal_assessment(d,'BUY')[0],'ضعيفة')
        for missing in (0,1,2,3,6):
            d=self.decision(); d['checks']['BUY'][missing]=False
            grade,reason,gaps=signal_assessment(d,'BUY')
            self.assertEqual(grade,'ضعيفة'); self.assertTrue(gaps)

    def test_forced_bias_is_never_strong(self):
        d=self.decision(); d['forced']=True
        self.assertNotEqual(signal_assessment(d,'BUY')[0],'قوية')

    def test_tied_scores_are_weak(self):
        d=self.decision(); d['checks']['SELL']=[True]*7
        self.assertEqual(signal_assessment(d,'BUY')[0],'ضعيفة')

    def test_missing_inputs_not_fabricated_weakness(self):
        for d in ({}, {'checks':{'BUY':[True]*7}},dict(self.decision(),context={})):
            self.assertEqual(signal_assessment(d,'BUY')[0],'غير قابلة للتقييم')

    def test_followup_evaluates_original_side_not_new_opposite(self):
        text=trade_follow_message(active_trade('BUY'),self.decision('SELL'),NOW)
        self.assertIn('قوة دعم الشراء الآن: ضعيفة',text)
        self.assertNotIn('قوة دعم البيع الآن: قوية',text)
        for retained in ('وقف الخسارة','TP1','TP2','شروط الشراء','شروط البيع'):
            self.assertIn(retained,text)

    def test_grade_changes_and_unavailable_are_rendered(self):
        d=self.decision(); trade=active_trade()
        self.assertIn('الشراء الآن: قوية',trade_follow_message(trade,d,NOW))
        d['context']['phase']='pullback'
        self.assertIn('الشراء الآن: ضعيفة',trade_follow_message(trade,d,NOW))
        self.assertIn('غير قابلة للتقييم',trade_follow_message(trade,{},NOW))

    def test_entry_and_report_use_shared_grade_without_success_score(self):
        d=self.decision(); before=copy.deepcopy(d)
        for text in (entry(active_trade(),d),report_message(snapshot(d,NOW),d)):
            self.assertIn('قوة إشارة الشراء: قوية',text)
            self.assertIn('السبب:',text)
            self.assertNotIn('قوة نجاح الصفقة',text)
            self.assertNotIn('/10',text)
        self.assertEqual(d,before)


if __name__=='__main__': unittest.main()
