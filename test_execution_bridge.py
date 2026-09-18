import unittest
from execution_bridge import validate_signal
from mt5_demo_adapter import MT5DemoAdapter

def signal(forced=False):
    return {"id":"s1","side":"BUY","bar":"b","price_time":"t","forced":forced,
            "sl":2300.0,"tp1":2310.0,"checks":{"BUY":[True]*6+[False]}}

class FakeBroker:
    def __init__(self,demo=True,positions=0): self.demo=demo; self.positions=positions; self.orders=[]
    def account_is_demo(self): return self.demo
    def open_positions(self,symbol): return self.positions
    def submit_market(self,req): self.orders.append(req); return {"ok":True,"ticket":"demo-1"}
    def close_position(self,ticket): return {"ok":True}

class Tests(unittest.TestCase):
    def test_live_blocked(self): self.assertEqual(validate_signal(signal(),False)[1],"live_account_blocked")
    def test_forced_blocked(self): self.assertEqual(validate_signal(signal(True),True)[1],"best_available_bias_blocked")
    def test_position_limit(self): self.assertEqual(validate_signal(signal(),True,1)[1],"position_limit")
    def test_demo_exec_and_duplicate(self):
        b=FakeBroker(); a=MT5DemoAdapter(b)
        self.assertTrue(a.execute(signal(),0.01)["ok"])
        self.assertEqual(a.execute(signal(),0.01)["reason"],"duplicate_order")
        self.assertEqual(len(b.orders),1)

if __name__=="__main__": unittest.main()
