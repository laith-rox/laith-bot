"""Safety regression tests for the experimental Laith Telegram launcher."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import laith_experimental_v4 as launcher


class ExperimentalLaithLauncherSafety(unittest.TestCase):
    def test_missing_credentials_fail_closed_before_runtime_import(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                launcher.main()

    def test_existing_telegram_credentials_and_gold_only_guards(self):
        credentials = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "test-chat",
            "TWELVE_DATA_API_KEY": "test-key",
            "V4_BTC_SIGNALS_ENABLED": "1",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
            "V4_BTC_M5_QUICK_ENABLED": "1",
        }
        runtime = MagicMock()
        runtime.parser.return_value.parse_args.return_value = object()
        with patch.dict(os.environ, credentials, clear=True):
            with patch.dict(sys.modules, {"v4_group_runtime": MagicMock(), "v4_runtime": runtime}):
                launcher.main()
            self.assertEqual(os.environ["V4_TELEGRAM_BOT_TOKEN"], credentials["TELEGRAM_BOT_TOKEN"])
            self.assertEqual(os.environ["V4_TELEGRAM_CHAT_ID"], credentials["TELEGRAM_CHAT_ID"])
            self.assertEqual(os.environ["V4_TWELVE_DATA_API_KEY"], credentials["TWELVE_DATA_API_KEY"])
            self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
            for name in ("V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED", "V4_BTC_M5_QUICK_ENABLED"):
                self.assertEqual(os.environ[name], "0")
            runtime.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
