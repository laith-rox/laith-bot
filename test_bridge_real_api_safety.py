import importlib.util
import os
import unittest

os.environ.setdefault("BRIDGE_CLIENT_TOKEN", "test-client")
os.environ.setdefault("BRIDGE_PUBLISH_TOKEN", "test-publish")
os.environ.setdefault("BRIDGE_HMAC_SECRET", "test-secret")
os.environ["BRIDGE_ENABLED"] = "false"
os.environ["REAL_BRIDGE_ARMED"] = "false"
os.environ["REAL_FIXED_VOLUME"] = "0"

spec = importlib.util.spec_from_file_location("bridge_real_api_under_test", "bridge_real_api.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class RealBridgeFailClosedTests(unittest.TestCase):
    def setUp(self):
        bridge.REAL_ARMED = False
        bridge.FIXED_VOLUME = 0.0
        bridge._runtime_enabled = False

    def test_publish_rejected_when_disarmed(self):
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_not_armed")

    def test_publish_rejected_when_volume_unconfigured(self):
        bridge.REAL_ARMED = True
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_volume_not_configured")

    def test_publish_rejected_when_kill_switch_off(self):
        bridge.REAL_ARMED = True
        bridge.FIXED_VOLUME = 0.01
        ok, reason = bridge._validate_publish({})
        self.assertFalse(ok)
        self.assertEqual(reason, "kill_switch")

    def test_manage_rejected_when_disarmed(self):
        ok, reason = bridge._validate_manage({})
        self.assertFalse(ok)
        self.assertEqual(reason, "real_not_armed")


if __name__ == "__main__":
    unittest.main()
