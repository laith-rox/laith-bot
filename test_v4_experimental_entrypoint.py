"""Guardrails for the existing experimental Laith -> V4 entrypoint."""
import os
import unittest
from unittest.mock import patch
import laith_experimental_v4


class ExperimentalEntrypointTests(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                laith_experimental_v4.main()

    def test_uses_experimental_credentials_and_separate_db(self):
        env = {"TELEGRAM_BOT_TOKEN": "demo-token", "TELEGRAM_CHAT_ID": "123",
               "TWELVE_DATA_API_KEY": "demo-key"}
        with patch.dict(os.environ, env, clear=True):
            with patch("v4_runtime.run") as run, patch("v4_runtime.parser") as parser:
                laith_experimental_v4.main()
                run.assert_called_once_with(parser.return_value.parse_args.return_value)
                self.assertEqual(os.environ["V4_TELEGRAM_BOT_TOKEN"], "demo-token")
                self.assertEqual(os.environ["V4_TELEGRAM_CHAT_ID"], "123")
                self.assertEqual(os.environ["V4_TWELVE_DATA_API_KEY"], "demo-key")
                self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
                self.assertEqual(os.environ["V4_BTC_SIGNALS_ENABLED"], "0")  # BTC disabled by default on gold experiment
                self.assertEqual(os.environ["V4_BTC_QUARTERLY_REPORTS_ENABLED"], "0")
                self.assertEqual(os.environ["V4_BTC_M5_QUICK_ENABLED"], "0")  # no BTC quick signals by default


    def test_gold_launcher_overrides_stale_bitcoin_opt_ins(self):
        env = {"TELEGRAM_BOT_TOKEN": "demo-token", "TELEGRAM_CHAT_ID": "123",
               "TWELVE_DATA_API_KEY": "demo-key",
               "V4_BTC_SIGNALS_ENABLED": "1",
               "V4_BTC_QUARTERLY_REPORTS_ENABLED": "1",
               "V4_BTC_M5_QUICK_ENABLED": "1"}
        with patch.dict(os.environ, env, clear=True):
            with patch("v4_runtime.run"), patch("v4_runtime.parser"):
                laith_experimental_v4.main()
                for name in ("V4_BTC_SIGNALS_ENABLED",
                             "V4_BTC_QUARTERLY_REPORTS_ENABLED",
                             "V4_BTC_M5_QUICK_ENABLED"):
                    self.assertEqual(os.environ[name], "0")

    def test_preserves_legacy_database_and_blocks_unverified_startup(self):
        # Missing a market credential must not rewrite any existing V4 settings.
        env = {"TELEGRAM_BOT_TOKEN": "demo-token", "TELEGRAM_CHAT_ID": "123",
               "V4_DB_PATH": "/data/laith.db", "V4_BTC_SIGNALS_ENABLED": "1"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                laith_experimental_v4.main()
            self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith.db")
            self.assertEqual(os.environ["V4_BTC_SIGNALS_ENABLED"], "1")

    def test_gold_launcher_uses_isolated_db_without_mt5_credentials(self):
        env = {"TELEGRAM_BOT_TOKEN": "demo-token", "TELEGRAM_CHAT_ID": "123",
               "TWELVE_DATA_API_KEY": "demo-key"}
        with patch.dict(os.environ, env, clear=True):
            with patch("v4_runtime.run") as run, patch("v4_runtime.parser"):
                laith_experimental_v4.main()
                run.assert_called_once()
                self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
                self.assertNotIn("MT5_PASSWORD", os.environ)


if __name__ == "__main__":
    unittest.main()
