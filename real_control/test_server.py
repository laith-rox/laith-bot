import importlib
import os
import unittest

os.environ["REAL_CONTROL_ARMING_ALLOWED"] = "false"
os.environ.pop("REAL_CONTROL_OWNER_TOKEN", None)

import server


class RealControlFailClosedTests(unittest.TestCase):
    def test_defaults_locked(self):
        s = server._status()
        self.assertTrue(s["locked"])
        self.assertFalse(s["armed"])
        self.assertTrue(s["emergency_stop"])
        self.assertFalse(s["execution_enabled"])
        self.assertFalse(s["trade_endpoint_present"])

    def test_no_owner_token_by_default(self):
        self.assertFalse(server.OWNER_TOKEN)


if __name__ == "__main__":
    unittest.main()
