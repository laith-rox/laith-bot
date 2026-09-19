import importlib
import os
import sys
import unittest

os.environ.setdefault("BRIDGE_CLIENT_TOKEN", "client-token-for-tests")
os.environ.setdefault("BRIDGE_PUBLISH_TOKEN", "publish-token-for-tests")
os.environ.setdefault("BRIDGE_HMAC_SECRET", "hmac-secret-for-tests")
os.environ.setdefault("BRIDGE_ENABLED", "true")

if "bridge_api" in sys.modules:
    del sys.modules["bridge_api"]
bridge_api = importlib.import_module("bridge_api")


class BridgeValidationTests(unittest.TestCase):
    def setUp(self):
        bridge_api._runtime_enabled = True

    def test_open_requires_strict_demo_gold_fixed_lot(self):
        payload = {
            "mode": "DEMO",
            "key": "open-test",
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": 0.01,
            "sl": 3900,
            "tp": 4100,
            "forced": False,
            "checks": {"BUY": [True, True, True, True, True, True, False]},
        }
        self.assertEqual(bridge_api._validate_publish(payload), (True, "approved"))

    def test_manage_modify_and_close(self):
        modify = {
            "mode": "DEMO",
            "key": "modify-test",
            "symbol": "XAUUSD",
            "action": "MODIFY",
            "sl": 4000,
            "tp": 4100,
            "reason": "profit_protect",
        }
        close = {
            "mode": "DEMO",
            "key": "close-test",
            "symbol": "XAUUSD",
            "action": "CLOSE",
            "reason": "emergency_reversal",
        }
        self.assertEqual(bridge_api._validate_manage(modify), (True, "approved"))
        self.assertEqual(bridge_api._validate_manage(close), (True, "approved"))

    def test_wire_formats_are_separate(self):
        open_item = {
            "action": "OPEN",
            "key": "o1",
            "ts": 1,
            "symbol": "XAUUSD",
            "side": "BUY",
            "volume": "0.01",
            "sl": "3900.00000",
            "tp": "4100.00000",
        }
        close_item = {
            "action": "CLOSE",
            "key": "c1",
            "ts": 1,
            "symbol": "XAUUSD",
            "sl": "0.00000",
            "tp": "0.00000",
        }
        self.assertTrue(bridge_api._wire_command(open_item).startswith("CMD|DEMO|"))
        self.assertTrue(bridge_api._wire_command(close_item).startswith("ACT|DEMO|ACTION|"))


if __name__ == "__main__":
    unittest.main()
