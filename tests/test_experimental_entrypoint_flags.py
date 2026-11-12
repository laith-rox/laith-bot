"""Regression tests for the gold-only experimental Telegram entrypoint."""
import os
import sys
import types
import unittest
from unittest.mock import patch

import laith_experimental_v4


class ExperimentalEntrypointFlagsTests(unittest.TestCase):
    def _run(self, overrides=None):
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "test-chat",
            "TWELVE_DATA_API_KEY": "test-market-key",
        }
        env.update(overrides or {})
        runtime = types.ModuleType("v4_runtime")
        runtime.parser = lambda: types.SimpleNamespace(parse_args=lambda: ())
        calls = []
        runtime.run = lambda args: calls.append(args)
        group = types.ModuleType("v4_group_runtime")
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(sys.modules, {"v4_runtime": runtime, "v4_group_runtime": group}):
                laith_experimental_v4.main()
                flags = {name: os.environ[name] for name in (
                    "V4_BTC_SIGNALS_ENABLED",
                    "V4_BTC_QUARTERLY_REPORTS_ENABLED",
                    "V4_BTC_M5_QUICK_ENABLED",
                )}
                db = os.environ["V4_DB_PATH"]
        return flags, db, calls

    def test_gold_only_defaults_disable_legacy_bitcoin_publishers(self):
        flags, db, calls = self._run()
        self.assertEqual(set(flags.values()), {"0"})
        self.assertEqual(db, "/data/laith_v4_experiment.db")
        self.assertEqual(len(calls), 1)

    def test_explicit_btc_opt_in_is_not_overwritten(self):
        flags, _, _ = self._run({"V4_BTC_SIGNALS_ENABLED": "1"})
        self.assertEqual(flags["V4_BTC_SIGNALS_ENABLED"], "1")
        self.assertEqual(flags["V4_BTC_QUARTERLY_REPORTS_ENABLED"], "0")


if __name__ == "__main__":
    unittest.main()
