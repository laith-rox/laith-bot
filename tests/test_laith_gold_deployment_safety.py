"""Regression checks for the isolated manual-only Laith gold launcher."""
import os
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import laith_experimental_v4 as launcher


class LauncherSafetyTests(unittest.TestCase):
    def test_docker_starts_gold_launcher(self):
        dockerfile = (ROOT / "Dockerfile.btc-experimental").read_text()
        self.assertIn('CMD ["python", "laith_experimental_v4.py"]', dockerfile)

    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": " ", "TELEGRAM_CHAT_ID": "1", "TWELVE_DATA_API_KEY": "key"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_missing_credentials"):
                launcher.main()

    def test_btc_symbol_fails_before_runtime_import(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "1", "TWELVE_DATA_API_KEY": "key", "SYMBOL": "BTCUSD"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "experimental_laith_non_gold_symbol"):
                launcher.main()

    def test_launcher_has_no_order_execution_calls(self):
        source = (ROOT / "laith_experimental_v4.py").read_text()
        for forbidden in ("order_send(", "mt5.order_send(", "place_order(", "execute_trade("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
