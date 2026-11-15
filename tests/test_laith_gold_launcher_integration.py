"""Integration regression for the existing experimental Laith gold launcher.

No network, Telegram delivery, broker calls, or live orders are made.
"""
import os
import sys
import types
import unittest
from unittest.mock import patch

import laith_experimental_v4 as launcher


class ExperimentalGoldLauncherIntegrationTests(unittest.TestCase):
    def test_gold_launch_preserves_telegram_and_isolates_database(self):
        captured = {}
        runtime = types.ModuleType("v4_runtime")
        runtime.parser = lambda: types.SimpleNamespace(parse_args=lambda: types.SimpleNamespace())
        def run(args):
            captured.update({k: os.environ.get(k) for k in (
                "SYMBOL", "V4_TELEGRAM_BOT_TOKEN", "V4_TELEGRAM_CHAT_ID",
                "V4_TWELVE_DATA_API_KEY", "V4_DB_PATH",
                "V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED",
                "V4_BTC_M5_QUICK_ENABLED",
            )})
        runtime.run = run
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "existing-token",
            "TELEGRAM_CHAT_ID": "existing-chat",
            "TWELVE_DATA_API_KEY": "existing-market-key",
            "SYMBOL": "XAU/USD",
            "V4_BTC_SIGNALS_ENABLED": "1",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
            "V4_BTC_M5_QUICK_ENABLED": "1",
        }, clear=True), patch.dict(sys.modules, {
            "v4_group_runtime": types.ModuleType("v4_group_runtime"),
            "v4_runtime": runtime,
        }):
            launcher.main()
        self.assertEqual(captured, {
            "SYMBOL": "XAUUSD",
            "V4_TELEGRAM_BOT_TOKEN": "existing-token",
            "V4_TELEGRAM_CHAT_ID": "existing-chat",
            "V4_TWELVE_DATA_API_KEY": "existing-market-key",
            "V4_DB_PATH": "/data/laith_v4_experiment.db",
            "V4_BTC_SIGNALS_ENABLED": "0",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "0",
            "V4_BTC_M5_QUICK_ENABLED": "0",
        })


if __name__ == "__main__":
    unittest.main()
