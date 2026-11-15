"""Exercise gold-only environment handoff without starting Telegram or trading."""
import os
import sys
import types
import unittest
from unittest.mock import patch

import laith_experimental_v4 as launcher


class GoldHandoffTests(unittest.TestCase):
    def test_launcher_normalizes_gold_and_disables_legacy_btc(self):
        captured = {}
        fake_runtime = types.ModuleType("v4_runtime")
        fake_runtime.parser = lambda: types.SimpleNamespace(parse_args=lambda: object())
        def fake_run(_args):
            captured.update({k: os.environ.get(k) for k in (
                "SYMBOL", "V4_TELEGRAM_BOT_TOKEN", "V4_TELEGRAM_CHAT_ID",
                "V4_TWELVE_DATA_API_KEY", "V4_DB_PATH",
                "V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED",
                "V4_BTC_M5_QUICK_ENABLED")})
        fake_runtime.run = fake_run
        with patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "123",
            "TWELVE_DATA_API_KEY": "test-key",
            "SYMBOL": "xau/usd",
            "V4_BTC_SIGNALS_ENABLED": "1",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
            "V4_BTC_M5_QUICK_ENABLED": "1",
        }, clear=True), patch.dict(sys.modules, {
            "v4_runtime": fake_runtime,
            "v4_group_runtime": types.ModuleType("v4_group_runtime"),
        }):
            launcher.main()
        self.assertEqual(captured["SYMBOL"], "XAUUSD")
        self.assertEqual(captured["V4_DB_PATH"], "/data/laith_v4_experiment.db")
        self.assertEqual(captured["V4_TELEGRAM_BOT_TOKEN"], "test-token")
        self.assertEqual(captured["V4_TELEGRAM_CHAT_ID"], "123")
        self.assertEqual(captured["V4_TWELVE_DATA_API_KEY"], "test-key")
        for name in ("V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED",
                     "V4_BTC_M5_QUICK_ENABLED"):
            self.assertEqual(captured[name], "0")


if __name__ == "__main__":
    unittest.main()
