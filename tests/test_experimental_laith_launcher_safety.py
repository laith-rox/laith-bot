"""Safety regression tests for the experimental Telegram-only gold launcher."""
import os
import unittest
from unittest.mock import patch
import laith_experimental_v4


class ExperimentalLauncherSafetyTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "test-chat",
            "TWELVE_DATA_API_KEY": "test-key",
            "SYMBOL": "XAU/USD",
            "V4_BTC_SIGNALS_ENABLED": "1",
            "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
            "V4_BTC_M5_QUICK_ENABLED": "1",
        }

    def test_launcher_disables_legacy_btc_and_uses_separate_database(self):
        with patch.dict(os.environ, self.env, clear=True):
            with patch("v4_runtime.run") as run, patch("v4_runtime.parser") as parser:
                parser.return_value.parse_args.return_value = object()
                laith_experimental_v4.main()
                run.assert_called_once()
                self.assertEqual(os.environ["SYMBOL"], "XAUUSD")
                self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
                for key in ("V4_BTC_SIGNALS_ENABLED", "V4_BTC_QUARTERLY_REPORTS_ENABLED", "V4_BTC_M5_QUICK_ENABLED"):
                    self.assertEqual(os.environ[key], "0")
                self.assertEqual(os.environ["V4_TELEGRAM_BOT_TOKEN"], "test-token")

    def test_non_gold_symbol_fails_before_runtime(self):
        for symbol in ("BTCUSD", "ETHUSD", "XAGUSD", ""):
            with self.subTest(symbol=symbol), patch.dict(os.environ, {**self.env, "SYMBOL": symbol}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "experimental_laith_non_gold_symbol"):
                    laith_experimental_v4.main()

    def test_blank_credentials_fail_before_runtime(self):
        for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "TWELVE_DATA_API_KEY"):
            with self.subTest(key=key), patch.dict(os.environ, {**self.env, key: "  "}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                    laith_experimental_v4.main()


if __name__ == "__main__":
    unittest.main()
