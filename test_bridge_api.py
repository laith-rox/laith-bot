import importlib
from http.client import HTTPConnection
import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

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


class BridgeConnectivityTests(unittest.TestCase):
    def setUp(self):
        bridge_api._runtime_enabled = True
        bridge_api._client_state = None
        bridge_api._client_last_poll = None
        bridge_api._items.clear()
        self.server = bridge_api.ThreadingHTTPServer(("127.0.0.1", 0), bridge_api.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, payload=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request(method, path, json.dumps(payload) if payload is not None else None, headers or {})
        response = conn.getresponse()
        status, body = response.status, response.read().decode()
        conn.close()
        return status, body

    def test_only_authenticated_polling_updates_connectivity_and_never_fakes_state(self):
        status, _ = self.request("GET", "/next", headers={"X-Bridge-Token": "wrong"})
        self.assertEqual(status, 401)
        self.assertIsNone(bridge_api._client_last_poll)
        status, _ = self.request("GET", "/next", headers={"X-Bridge-Token": bridge_api.CLIENT_TOKEN})
        self.assertEqual(status, 200)
        _, raw = self.request("GET", "/health")
        health = json.loads(raw)
        self.assertTrue(health["client_poll_fresh"])
        self.assertFalse(health["client_state_fresh"])
        self.assertIsNone(health["client_last_seen_age"])
        bridge_api._client_last_poll = time.time() - 11
        _, raw = self.request("GET", "/health")
        self.assertFalse(json.loads(raw)["client_poll_fresh"])

    def test_ack_log_distinguishes_broker_rejection_from_filled_order(self):
        for success, reason, ticket in [(False, "retcode_10016", "0"),
                                        (True, "retcode_10009", "12345")]:
            key = "ack-test-" + str(success)
            bridge_api._items[key] = {"action": "OPEN", "side": "BUY", "ack": None}
            with patch("builtins.print") as log:
                status, _ = self.request("POST", "/ack", {
                    "key": key, "ok": success, "reason": reason, "ticket": ticket,
                }, {"X-Bridge-Token": bridge_api.CLIENT_TOKEN})
            self.assertEqual(status, 200)
            records = [json.loads(call.args[0].split(" ", 1)[1])
                       for call in log.call_args_list
                       if call.args and str(call.args[0]).startswith("bridge_order_ack ")]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["ok"], success)
            self.assertEqual(records[0]["reason"], reason)
            self.assertEqual(records[0]["ticket"], ticket)


if __name__ == "__main__":
    unittest.main()
