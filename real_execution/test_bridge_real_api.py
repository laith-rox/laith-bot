import importlib.util
import os
import unittest

os.environ["REAL_BRIDGE_ARMED"] = "false"
os.environ["REAL_EXECUTION_ENABLED"] = "false"
os.environ["REAL_FIXED_VOLUME"] = "0"
for k in ("REAL_BRIDGE_CLIENT_TOKEN","REAL_BRIDGE_PUBLISH_TOKEN","REAL_BRIDGE_HMAC_SECRET"):
    os.environ.pop(k, None)

spec = importlib.util.spec_from_file_location("bridge_real_api_under_test", "bridge_real_api.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class RealBridgeFailClosedTests(unittest.TestCase):
    def setUp(self):
        bridge.REAL_ARMED = False
        bridge.EXECUTION_ENABLED = False
        bridge.FIXED_VOLUME = 0.0

    def test_status_is_not_ready_by_default(self):
        s = bridge._status()
        self.assertFalse(s["armed"])
        self.assertFalse(s["execution_enabled"])
        self.assertFalse(s["configured"])
        self.assertFalse(s["ready"])

    def test_publish_rejected_when_disarmed(self):
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_not_armed")

    def test_execution_switch_is_independent(self):
        bridge.REAL_ARMED = True
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_execution_disabled")

    def test_volume_must_be_explicitly_configured(self):
        bridge.REAL_ARMED = True
        bridge.EXECUTION_ENABLED = True
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_volume_not_configured")


if __name__ == "__main__":
    unittest.main()
