from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from v3_backtest import _macro_for
from v3_global_data import Observation

UTC = timezone.utc


class BacktestMacroSourceTests(unittest.TestCase):
    def test_twelve_proxy_history_uses_proxy_snapshot(self):
        history = {
            "usd_proxy": [Observation(datetime(2026, 9, 14).date(), 100.0), Observation(datetime(2026, 9, 15).date(), 99.0)],
            "bond_proxy": [Observation(datetime(2026, 9, 14).date(), 90.0), Observation(datetime(2026, 9, 15).date(), 91.0)],
            "vol_proxy": [Observation(datetime(2026, 9, 14).date(), 20.0), Observation(datetime(2026, 9, 15).date(), 21.0)],
            "equity_proxy": [Observation(datetime(2026, 9, 14).date(), 600.0), Observation(datetime(2026, 9, 15).date(), 601.0)],
            "oil_proxy": [Observation(datetime(2026, 9, 14).date(), 80.0), Observation(datetime(2026, 9, 15).date(), 81.0)],
        }
        provider = SimpleNamespace(history=history, source="twelve_proxy")
        snap = _macro_for(provider, datetime(2026, 9, 16, 12, tzinfo=UTC))
        self.assertEqual(snap["source"], "twelve_proxy")
        self.assertEqual(snap["coverage"], 5)
        self.assertEqual(snap["primary_coverage"], 2)

    def test_fred_history_uses_fred_snapshot(self):
        history = {
            "usd_broad": [Observation(datetime(2026, 9, 14).date(), 100.0), Observation(datetime(2026, 9, 15).date(), 99.0)],
            "real_10y": [Observation(datetime(2026, 9, 14).date(), 2.0), Observation(datetime(2026, 9, 15).date(), 1.9)],
            "nominal_10y": [Observation(datetime(2026, 9, 14).date(), 4.0), Observation(datetime(2026, 9, 15).date(), 3.9)],
            "vix": [Observation(datetime(2026, 9, 14).date(), 15.0), Observation(datetime(2026, 9, 15).date(), 16.0)],
            "oil_wti": [Observation(datetime(2026, 9, 14).date(), 90.0), Observation(datetime(2026, 9, 15).date(), 91.0)],
        }
        provider = SimpleNamespace(history=history, source="fred")
        snap = _macro_for(provider, datetime(2026, 9, 16, 12, tzinfo=UTC))
        self.assertEqual(snap["source"], "fred")
        self.assertEqual(snap["coverage"], 5)
        self.assertEqual(snap["primary_coverage"], 2)


if __name__ == "__main__":
    unittest.main()
