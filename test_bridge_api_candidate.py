import os
import unittest
from unittest.mock import patch

os.environ.setdefault("BRIDGE_CLIENT_TOKEN","x")
os.environ.setdefault("BRIDGE_PUBLISH_TOKEN","x")
os.environ.setdefault("BRIDGE_HMAC_SECRET","x")
os.environ.setdefault("BRIDGE_ENABLED","true")
try:
    import bridge_api as api
except ModuleNotFoundError:
    import bridge_api_current as api


class SniperApiPolicyTests(unittest.TestCase):
    def payload(self, strength):
        checks=[True]*strength+[False]*(7-strength)
        return {
            "mode":"DEMO",
            "trade_mode":"SNIPER",
            "key":f"auto:20261002T193500:SNIPER:BUY:C1:S{strength}",
            "symbol":"XAUUSD",
            "side":"BUY",
            "volume":api.FIXED_VOLUME,
            "sl":4100.0,
            "tp":4200.0,
            "forced":False,
            "checks":{"BUY":checks},
        }

    def test_three_and_four_are_allowed_when_not_countertrend(self):
        with patch.object(api,"_runtime_enabled",True), patch.object(api,"_market_countertrend",return_value=False):
            for strength in (3,4):
                with self.subTest(strength=strength):
                    self.assertEqual(api._validate_publish(self.payload(strength)),(True,"approved"))

    def test_weak_countertrend_sniper_is_blocked(self):
        with patch.object(api,"_runtime_enabled",True), patch.object(api,"_market_countertrend",return_value=True):
            self.assertEqual(api._validate_publish(self.payload(3)),(False,"countertrend_market_block"))
            self.assertEqual(api._validate_publish(self.payload(5)),(False,"countertrend_market_block"))

    def test_six_and_seven_countertrend_sniper_are_allowed(self):
        with patch.object(api,"_runtime_enabled",True), patch.object(api,"_market_countertrend",return_value=True):
            self.assertEqual(api._validate_publish(self.payload(6)),(True,"approved"))
            self.assertEqual(api._validate_publish(self.payload(7)),(True,"approved"))

    def test_strength_suffix_must_match_checks(self):
        data=self.payload(4)
        data["checks"]["BUY"]=[True]*3+[False]*4
        with patch.object(api,"_runtime_enabled",True), patch.object(api,"_market_countertrend",return_value=False):
            self.assertEqual(api._validate_publish(data),(False,"signal_strength_mismatch"))


if __name__=="__main__":
    unittest.main()