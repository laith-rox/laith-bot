"""Contract tests for the isolated Telegram-only experimental Laith launcher."""
import os
import unittest
from unittest.mock import patch, MagicMock

import laith_experimental_v4 as launcher


class ExperimentalLauncherContract(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                launcher.main()

    def test_gold_only_launcher_preserves_existing_credentials_and_db(self):
        runtime = MagicMock()
        runtime.parser.return_value.parse_args.return_value = object()
        group = MagicMock()
        existing = {
            "TELEGRAM_BOT_TOKEN": "existing-token",
            "TELEGRAM_CHAT_ID": "existing-chat",
            "TWELVE_DATA_API_KEY": "existing-market-key",
            "V4_BTC_SIGNALS_ENABLED": "1",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
            "V4_BTC_M5_QUICK_ENABLED": "1",
        }
        with patch.dict(os.environ, existing, clear=True):
            with patch.dict("sys.modules", {"v4_runtime": runtime, "v4_group_runtime": group}):
                launcher.main()
                self.assertEqual(os.environ["V4_TELEGRAM_BOT_TOKEN"], "existing-token")
                self.assertEqual(os.environ["V4_TELEGRAM_CHAT_ID"], "existing-chat")
                self.assertEqual(os.environ["V4_TWELVE_DATA_API_KEY"], "existing-market-key")
                self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
                for name in ("V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED", "V4_BTC_M5_QUICK_ENABLED"):
                    self.assertEqual(os.environ[name], "0")
                runtime.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
