import unittest
from adaptive_sniper_engine import decide

class AdaptiveSniperTests(unittest.TestCase):
    def base(self, **kw):
        x=dict(buy_score=5,sell_score=1,rsi=60,atr=2.0,atr_baseline=1.5,
               ema_fast=11,ema_slow=10,close=12,recent_high=11.5,recent_low=9,
               momentum=1.0,hour_local=14)
        x.update(kw); return decide(**x)

    def test_daytime_strong_setup_prefers_official_main(self):
        d=self.base(buy_score=6,hour_local=8)
        self.assertEqual((d.mode,d.side),("MAIN","BUY"))

    def test_sniper_requires_momentum_rsi_plus_context(self):
        d=self.base(hour_local=21)
        self.assertEqual((d.mode,d.side),("SNIPER","BUY"))

    def test_no_blind_rsi_entry(self):
        d=self.base(momentum=-1,ema_fast=9,ema_slow=10,close=10,recent_high=12)
        self.assertEqual(d.mode,"WAIT")

    def test_night_does_not_raise_risk_without_exceptional_evidence(self):
        d=self.base(hour_local=21,buy_score=5,atr=1.5,atr_baseline=1.5,close=11)
        self.assertEqual(d.risk_mult,1.0)

    def test_night_boost_is_capped(self):
        d=self.base(hour_local=21,buy_score=7,atr=2.0,atr_baseline=1.5)
        self.assertLessEqual(d.risk_mult,1.20)

if __name__=="__main__":
    unittest.main()
