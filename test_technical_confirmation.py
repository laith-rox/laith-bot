import unittest
from technical_confirmation import analyze,patterns

def row(o,h,l,c,v=100):
    return {"open":o,"high":h,"low":l,"close":c,"tick_volume":v}

class TechnicalConfirmationTests(unittest.TestCase):
    def test_bullish_engulfing_detected(self):
        rows=[row(100+i*.1,101+i*.1,99+i*.1,100.1+i*.1) for i in range(60)]
        rows[-2]=row(106,106.2,104.8,105)
        rows[-1]=row(104.9,106.5,104.7,106.2)
        bull,bear,neutral=patterns(rows)
        self.assertIn("bullish_engulfing",bull)

    def test_indicator_analysis_returns_scores(self):
        rows=[row(100+i*.2,100.4+i*.2,99.8+i*.2,100.3+i*.2,100+i) for i in range(80)]
        out=analyze(rows)
        self.assertGreater(out["bull_score"],out["bear_score"])
        self.assertIsNotNone(out["vwap"])
        self.assertIn("macd_hist",out)

if __name__=="__main__": unittest.main()
