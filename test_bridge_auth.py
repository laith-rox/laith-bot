import unittest
from bridge_auth import sign,verify

class AuthTests(unittest.TestCase):
 def test_valid(self):
  p={"mode":"DEMO","ts":1000,"key":"x"}; self.assertTrue(verify(p,sign(p,"secret"),"secret",now=1000)[0])
 def test_bad_secret(self):
  p={"mode":"DEMO","ts":1000}; self.assertEqual(verify(p,sign(p,"a"),"b",now=1000)[1],"bad_signature")
 def test_stale(self):
  p={"mode":"DEMO","ts":900}; self.assertEqual(verify(p,sign(p,"s"),"s",now=1000)[1],"stale_command")
 def test_live_block(self):
  p={"mode":"LIVE","ts":1000}; self.assertEqual(verify(p,sign(p,"s"),"s",now=1000)[1],"non_demo_command")

if __name__=="__main__": unittest.main()
