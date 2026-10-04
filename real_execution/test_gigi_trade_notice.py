import json
import unittest

import gigi_trade_notice


def signal(side="BUY"):
    return {
        "bar":"2026-10-04 18:15:00",
        "side":side,
        "mode":"MAIN",
        "risk_distance":5.0,
        "target_r":2.0,
        "checks":{side:[True,True,True,True,False,False,False]},
        "setup":{"name":"BREAKOUT_RETEST"},
        "gigi_context":{"alignment":"SUPPORT","score":2},
        "crowding":{"dominant_risk":"BALANCED"},
        "uncertainty":{"state":"NORMAL"},
        "readiness":{"state":"READY"},
    }


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self): return b'{"ok":true,"duplicate":false}'


class NoticeTests(unittest.TestCase):
    def test_rejected_buy_keeps_trade_levels(self):
        out=gigi_trade_notice.build(signal("BUY"),4300,"REJECTED","aggregate_risk_budget")
        self.assertAlmostEqual(out["levels"]["sl"],4295)
        self.assertAlmostEqual(out["levels"]["tp"],4310)
        self.assertIn("رفضها حاجز التنفيذ",out["text"])
        self.assertIn("aggregate_risk_budget",out["text"])

    def test_sell_levels(self):
        out=gigi_trade_notice.build(signal("SELL"),4300,"PUBLISHED")
        self.assertAlmostEqual(out["levels"]["sl"],4305)
        self.assertAlmostEqual(out["levels"]["tp"],4290)

    def test_no_side_is_not_a_trade_notice(self):
        s=signal("BUY"); s["side"]=None
        self.assertIsNone(gigi_trade_notice.build(s,4300,"REJECTED","no_side"))

    def test_unconfigured_relay_fails_closed_but_returns_notice(self):
        out=gigi_trade_notice.send(signal(),4300,"REJECTED","test",relay_url="",relay_token="")
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"decision_relay_not_configured")
        self.assertIn("notice",out)

    def test_send_uses_relay_without_execution_path(self):
        seen={}
        def opener(req,timeout=0):
            seen["body"]=json.loads(req.data.decode("utf-8"))
            seen["token"]=req.headers.get("X-relay-token")
            return FakeResponse()
        out=gigi_trade_notice.send(signal(),4300,"REJECTED","session_closed",
            relay_url="https://relay.invalid/signal",relay_token="secret",opener=opener)
        self.assertTrue(out["ok"])
        self.assertIn("session_closed",seen["body"]["text"])


if __name__=="__main__":
    unittest.main()
