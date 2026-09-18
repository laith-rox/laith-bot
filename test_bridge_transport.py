import unittest
from bridge_transport import DemoCommandQueue

class QueueTests(unittest.TestCase):
 def p(self,key="a",ts=1000): return {"mode":"DEMO","ts":ts,"key":key,"symbol":"XAUUSD","side":"BUY","volume":.01,"sl":2300,"tp":2310}
 def test_roundtrip(self):
  q=DemoCommandQueue("s"); self.assertTrue(q.publish(self.p())["ok"]); cmd=q.next(now=1000); self.assertEqual(cmd["payload"]["key"],"a"); self.assertTrue(q.acknowledge("a",{"ok":True,"ticket":"demo-1"})["ok"])
 def test_duplicate(self):
  q=DemoCommandQueue("s"); q.publish(self.p()); self.assertEqual(q.publish(self.p())["reason"],"duplicate_order")
 def test_live_rejected(self):
  q=DemoCommandQueue("s"); p=self.p(); p["mode"]="LIVE"
  with self.assertRaises(ValueError): q.publish(p)
 def test_stale_not_delivered(self):
  q=DemoCommandQueue("s"); q.publish(self.p(ts=900)); self.assertIsNone(q.next(now=1000))

if __name__=="__main__": unittest.main()
