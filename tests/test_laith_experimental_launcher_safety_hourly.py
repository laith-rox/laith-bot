"""Safety regression tests for the experimental Laith Telegram-only launcher."""
import os
import sys
import types
import unittest
from unittest.mock import patch

import laith_experimental_v4


class ExperimentalLauncherSafetyTests(unittest.TestCase):
    def test_missing_credentials_never_starts_runtime(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                laith_experimental_v4.main()

    def test_gold_only_isolation_and_manual_runtime_handoff(self):
        runtime = types.ModuleType("v4_runtime")
        group = types.ModuleType("v4_group_runtime")
        calls = []
        runtime.parser = lambda: types.SimpleNamespace(parse_args=lambda: "parsed")
        runtime.run = lambda args: calls.append(args)
        env = {
            "TELEGRAM_BOT_TOKEN": "dummy",
            "TELEGRAM_CHAT_ID": "dummy-chat",
            "TWELVE_DATA_API_KEY": "dummy-market",
            "V4_BTC_SIGNALS_ENABLED": "1",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
            "V4_BTC_M5_QUICK_ENABLED": "1",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(sys.modules, {"v4_runtime": runtime, "v4_group_runtime": group}):
                laith_experimental_v4.main()
                self.assertEqual(calls, ["parsed"])
                self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
                self.assertEqual(os.environ["V4_TELEGRAM_BOT_TOKEN"], "dummy")
                self.assertEqual(os.environ["V4_TELEGRAM_CHAT_ID"], "dummy-chat")
                self.assertEqual(os.environ["V4_TWELVE_DATA_API_KEY"], "dummy-market")
                for name in ("V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED", "V4_BTC_M5_QUICK_ENABLED"):
                    self.assertEqual(os.environ[name], "0")


if __name__ == "__main__":
    unittest.main()
