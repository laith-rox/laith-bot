import os
import tempfile
import time
import unittest
from unittest.mock import patch

from storage import Store
from v4_mt5_bridge import bridge_mode, publish_official_order


class V4MT5BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "v4.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def trade(self, **overrides):
        now = time.time()
        trade = {
            "id": "v4-test-1",
            "generation": "V4",
            "paper_only": True,
            "status": "active",
            "side": "BUY",
            "entry": 4000.0,
            "stop": 3990.0,
            "tp1": 4010.0,
            "announced": now,
            "created": now,
        }
        trade.update(overrides)
        return trade

    @patch.dict(os.environ, {
        "V4_MT5_BRIDGE_ENABLED": "1",
        "V4_MT5_EXECUTION_MODE": "demo",
        "V4_MT5_DEMO_LOT": "0.01",
        "V4_MT5_MAX_LOT": "0.02",
    }, clear=False)
    def test_publishes_one_fresh_demo_order_and_deduplicates(self):
        trade = self.trade()
        first = publish_official_order(self.store, trade)
        second = publish_official_order(self.store, trade)
        self.assertIsNotNone(first)
        self.assertEqual(first["mode"], "demo")
        self.assertEqual(first["lot"], 0.01)
        self.assertIsNotNone(second)
        rows = self.store.db.execute("SELECT id,status FROM v4_exec_orders").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")

    @patch.dict(os.environ, {
        "V4_MT5_BRIDGE_ENABLED": "1",
        "V4_MT5_EXECUTION_MODE": "demo",
        "V4_MT5_MAX_SIGNAL_AGE_SECONDS": "60",
    }, clear=False)
    def test_stale_trade_is_not_published(self):
        trade = self.trade(announced=time.time() - 120)
        self.assertIsNone(publish_official_order(self.store, trade))

    @patch.dict(os.environ, {
        "V4_MT5_BRIDGE_ENABLED": "1",
        "V4_MT5_EXECUTION_MODE": "demo",
    }, clear=False)
    def test_invalid_levels_are_blocked(self):
        trade = self.trade(stop=4010.0)
        self.assertIsNone(publish_official_order(self.store, trade))

    @patch.dict(os.environ, {
        "V4_MT5_EXECUTION_MODE": "live",
        "V4_MT5_LIVE_ARMED": "NO",
    }, clear=False)
    def test_live_mode_fails_closed_without_explicit_arming(self):
        self.assertEqual(bridge_mode(), "disabled")


if __name__ == "__main__":
    unittest.main()
