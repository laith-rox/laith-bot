import unittest
from datetime import datetime, timedelta, timezone
from multi_timeframe_structure import analyze_structure


def rows(step, count, minutes, start=4200.0):
    out=[]; p=start; t=datetime(2026,9,1,tzinfo=timezone.utc)
    for i in range(count):
        o=p; c=p+step
        out.append({"datetime":(t+timedelta(minutes=i*minutes)).isoformat(),
                    "open":o,"high":max(o,c)+0.25,"low":min(o,c)-0.25,"close":c})
        p=c
    return out


class MultiTimeframeStructureTests(unittest.TestCase):
    def test_buy_requires_h4_context_m15_break_and_m5_confirmation(self):
        h1=rows(0.30,120,60,4200)
        m15=rows(0.02,50,15,4230)
        level=max(r["high"] for r in m15[-18:-2])
        m15[-2].update(open=level+0.2,low=level+0.1,high=level+1.0,close=level+0.8)
        m15[-1].update(open=level+0.5,low=level+0.1,high=level+1.3,close=level+1.1)
        m5=rows(0.15,50,5,level-5)
        x=analyze_structure(m5,m15,h1)
        self.assertEqual(x["h4_bias"],"UP")
        self.assertTrue(x["break_up"])
        self.assertEqual(x["side"],"BUY")

    def test_sell_requires_h4_context_m15_break_and_m5_confirmation(self):
        h1=rows(-0.30,120,60,4350)
        m15=rows(-0.02,50,15,4320)
        level=min(r["low"] for r in m15[-18:-2])
        m15[-2].update(open=level-0.2,high=level-0.1,low=level-1.0,close=level-0.8)
        m15[-1].update(open=level-0.5,high=level-0.1,low=level-1.3,close=level-1.1)
        m5=rows(-0.15,50,5,level+5)
        x=analyze_structure(m5,m15,h1)
        self.assertEqual(x["h4_bias"],"DOWN")
        self.assertTrue(x["break_down"])
        self.assertEqual(x["side"],"SELL")

    def test_countertrend_break_is_blocked(self):
        h1=rows(-0.30,120,60,4350)
        m15=rows(0.02,50,15,4300)
        level=max(r["high"] for r in m15[-18:-2])
        m15[-2].update(open=level+0.2,low=level+0.1,high=level+1.0,close=level+0.8)
        m15[-1].update(open=level+0.5,low=level+0.1,high=level+1.3,close=level+1.1)
        m5=rows(0.15,50,5,level-5)
        x=analyze_structure(m5,m15,h1)
        self.assertEqual(x["h4_bias"],"DOWN")
        self.assertIsNone(x["side"])


if __name__=="__main__":
    unittest.main()
