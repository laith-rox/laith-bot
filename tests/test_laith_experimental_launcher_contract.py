"""Deployment contract for the existing experimental Laith Telegram bot.

The launcher must never authorize unverified gold sessions or news, touch the
legacy DB, or route orders to a broker.
"""
import os
import unittest
from unittest.mock import patch

import laith_experimental_v4


class ExperimentalLauncherContractTests(unittest.TestCase):
    def test_missing_credentials_fail_before_runtime(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                laith_experimental_v4.main()

    def test_uses_existing_telegram_credentials_and_separate_database(self):
        fake = {
            "TELEGRAM_BOT_TOKEN": "existing-token",
            "TELEGRAM_CHAT_ID": "existing-chat",
            "TWELVE_DATA_API_KEY": "existing-market-key",
        }
        with patch.dict(os.environ, fake, clear=True):
            with patch("v4_runtime.parser") as parser, patch("v4_runtime.run") as run:
                parser.return_value.parse_args.return_value = object()
                laith_experimental_v4.main()
                run.assert_called_once()
                self.assertEqual(os.environ["V4_TELEGRAM_BOT_TOKEN"], fake["TELEGRAM_BOT_TOKEN"])
                self.assertEqual(os.environ["V4_TELEGRAM_CHAT_ID"], fake["TELEGRAM_CHAT_ID"])
                self.assertEqual(os.environ["V4_DB_PATH"], "/data/laith_v4_experiment.db")
                self.assertEqual(os.environ["V4_BTC_SIGNALS_ENABLED"], "0")
                self.assertEqual(os.environ["V4_BTC_QUARTERLY_REPORTS_ENABLED"], "0")
                self.assertEqual(os.environ["V4_BTC_M5_QUICK_ENABLED"], "0")
                self.assertNotIn("V4_VERIFIED_BROKER_SESSIONS", os.environ)
                self.assertNotIn("V4_VERIFIED_NEWS_EVENTS", os.environ)


if __name__ == "__main__":
    unittest.main()
