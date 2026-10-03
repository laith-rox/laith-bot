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



if __name__=="__main__":
    unittest.main()
