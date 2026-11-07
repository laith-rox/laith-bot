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


if __name__ == "__main__":
    unittest.main()
