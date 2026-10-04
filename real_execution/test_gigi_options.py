import json
import unittest
from datetime import datetime, timezone, timedelta

import gigi_options


def payload(rr=0.01, put_oi=100, call_oi=100):
    ts="2026-10-03 12:00:00"
    spot=380.0
    expiry=datetime(2026,10,30,tzinfo=timezone.utc)
    code=expiry.strftime("%y%m%d")
    opts=[]
    for cp,target_delta,iv,oi in [
        ("C",0.25,0.20,call_oi),
        ("P",-0.25,0.20+rr,put_oi),
    ]:
        strike=397 if cp=="C" else 367
        opts.append({
            "option":f"GLD{code}{cp}{int(strike*1000):08d}",
            "iv":iv,"delta":target_delta,"open_interest":oi,"volume":50,"gamma":0.02,
        })
    # Add extra strikes so the expiry is usable.
    for strike in range(320,441,10):
        gamma=0.08 if strike in (375,380,385) else 0.01
        opts.append({"option":f"GLD{code}C{int(strike*1000):08d}","iv":0.21,"delta":0.5,"open_interest":20,"volume":5,"gamma":gamma})
        opts.append({"option":f"GLD{code}P{int(strike*1000):08d}","iv":0.21,"delta":-0.5,"open_interest":20,"volume":5,"gamma":gamma})
    return {"timestamp":ts,"data":{"current_price":spot,"iv30":20.5,"options":opts}}


def term_payload(near_iv=0.30, far_iv=0.20):
    base = payload()
    spot = base["data"]["current_price"]
    options = []
    for expiry, iv in [
        (datetime(2026,10,16,tzinfo=timezone.utc), near_iv),
        (datetime(2026,11,20,tzinfo=timezone.utc), far_iv),
    ]:
        code = expiry.strftime("%y%m%d")
        for strike in (360,370,380,390,400):
            for cp, delta in (("C",0.5),("P",-0.5)):
                options.append({
                    "option":f"GLD{code}{cp}{int(strike*1000):08d}",
                    "iv":iv,
                    "delta":delta,
                    "open_interest":100,
                    "volume":10,
                    "gamma":0.02,
                })
        options.append({
            "option":f"GLD{code}C{int(397*1000):08d}",
            "iv":iv,"delta":0.25,"open_interest":100,"volume":10,"gamma":0.02,
        })
        options.append({
            "option":f"GLD{code}P{int(367*1000):08d}",
            "iv":iv,"delta":-0.25,"open_interest":100,"volume":10,"gamma":0.02,
        })
    base["data"]["options"] = options
    base["data"]["current_price"] = spot
    return base


class GigiOptionsTests(unittest.TestCase):
    def test_downside_skew_detected(self):
        out=gigi_options.parse(payload(rr=0.05))
        self.assertEqual(out["skew"],"DOWNSIDE_HEDGE_BID")
        self.assertGreater(out["rr25_put_minus_call"],0.03)
        self.assertFalse(out["directional_signal"])

    def test_upside_call_skew_detected(self):
        out=gigi_options.parse(payload(rr=-0.05))
        self.assertEqual(out["skew"],"UPSIDE_CALL_BID")

    def test_oi_imbalance_detected(self):
        out=gigi_options.parse(payload(rr=0.0,put_oi=20,call_oi=500))
        self.assertEqual(out["oi_state"],"CALL_HEAVY")

    def test_proxy_is_explicit(self):
        out=gigi_options.parse(payload())
        self.assertIn("GLD_options_not_COMEX",out["proxy_note"])

    def test_gamma_context_is_unsigned_and_non_directional(self):
        out=gigi_options.parse(payload())
        self.assertIn(out["gross_gamma_oi_context"],(
            "HIGH_NEAR_SPOT_CONVEXITY","MODERATE_NEAR_SPOT_CONVEXITY","DISTRIBUTED_CONVEXITY"
        ))
        self.assertIn("no_dealer_sign_inference",out["gamma_note"])
        self.assertFalse(out["directional_signal"])


    def test_fetch_has_stdlib_fallback_without_requests(self):
        original_requests = gigi_options.requests
        original_urlopen = gigi_options.urllib.request.urlopen
        original_cache = dict(gigi_options._cache)

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(payload()).encode("utf-8")

        try:
            gigi_options.requests=None
            gigi_options.urllib.request.urlopen=lambda req,timeout=15: FakeResponse()
            gigi_options._cache={"fetched_at":0.0,"value":None}
            out=gigi_options.fetch(now=12345)
            self.assertEqual(out["skew"],"BALANCED")
            self.assertIsNone(out["error"])
        finally:
            gigi_options.requests=original_requests
            gigi_options.urllib.request.urlopen=original_urlopen
            gigi_options._cache=original_cache


    def test_freshness_uses_underlying_last_trade_time(self):
        data=payload()
        data["timestamp"]="2026-10-03 03:43:53"
        data["data"]["last_trade_time"]="2026-10-02T15:59:59"
        out=gigi_options.parse(data)
        self.assertEqual(out["as_of"],"2026-10-02T15:59:59")
        self.assertEqual(out["snapshot_time"],"2026-10-03 03:43:53")


    def test_term_structure_backwardation_detected(self):
        out=gigi_options.parse(term_payload(near_iv=0.34,far_iv=0.20))
        self.assertEqual(out["term_structure"],"BACKWARDATION")
        self.assertGreater(out["term_iv_diff"],0.03)

    def test_term_structure_contango_detected(self):
        out=gigi_options.parse(term_payload(near_iv=0.18,far_iv=0.25))
        self.assertEqual(out["term_structure"],"CONTANGO")
        self.assertLess(out["term_iv_diff"],-0.03)

    def test_iv30_expected_move_is_non_directional(self):
        out=gigi_options.parse(payload())
        self.assertGreater(out["expected_move_1d_pct"],0)
        self.assertGreater(out["expected_move_5d_pct"],out["expected_move_1d_pct"])
        self.assertFalse(out["directional_signal"])


    def test_near_expiry_oi_cluster_is_unsigned_context(self):
        data=payload()
        data["timestamp"]="2026-10-27 12:00:00"
        code="261030"
        opts=[]
        for strike,oi in [(379,100),(380,1000),(381,120),(390,50)]:
            for cp,delta in (("C",0.5),("P",-0.5)):
                opts.append({
                    "option":f"GLD{code}{cp}{int(strike*1000):08d}",
                    "iv":0.21,
                    "delta":delta,
                    "open_interest":oi,
                    "volume":10,
                    "gamma":0.02,
                })
        opts.append({
            "option":f"GLD{code}C{int(397*1000):08d}",
            "iv":0.20,"delta":0.25,"open_interest":20,"volume":5,"gamma":0.01,
        })
        opts.append({
            "option":f"GLD{code}P{int(367*1000):08d}",
            "iv":0.21,"delta":-0.25,"open_interest":20,"volume":5,"gamma":0.01,
        })
        data["data"]["options"]=opts
        out=gigi_options.parse(data)
        self.assertIn(out["near_expiry_pin_state"],(
            "NEAR_EXPIRY_OI_CLUSTER_AT_SPOT","NEAR_EXPIRY_OI_CLUSTER_NEAR_SPOT"
        ))
        self.assertIn("not_directional",out["near_expiry_note"])



if __name__=="__main__":
    unittest.main()
