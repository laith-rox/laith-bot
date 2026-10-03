import unittest
from datetime import datetime, timezone, timedelta

import gigi_liquidity


def base_rows():
    t0=datetime(2026,10,1,tzinfo=timezone.utc)
    rows=[]
    for i in range(24):
        price=100.0 + (i%4)*0.05
        rows.append({
            "datetime":(t0+timedelta(minutes=5*i)).isoformat(),
            "open":price,
            "high":price+0.30,
            "low":price-0.30,
            "close":price+0.02,
            "tick_volume":100,
        })
    return rows


class GigiLiquidityTests(unittest.TestCase):
    def test_sell_side_sweep_is_bullish_pressure(self):
        rows=base_rows()
        prior_low=min(r["low"] for r in rows[-21:-1])
        rows[-1].update({
            "open":100.0,
            "high":100.2,
            "low":prior_low-0.20,
            "close":prior_low+0.15,
        })
        out=gigi_liquidity.analyze(rows)
        self.assertEqual(out["event"],"SELL_SIDE_SWEEP")
        self.assertEqual(out["pressure"],"BULLISH")

    def test_buy_side_sweep_is_bearish_pressure(self):
        rows=base_rows()
        prior_high=max(r["high"] for r in rows[-21:-1])
        rows[-1].update({
            "open":100.0,
            "high":prior_high+0.20,
            "low":99.8,
            "close":prior_high-0.15,
        })
        out=gigi_liquidity.analyze(rows)
        self.assertEqual(out["event"],"BUY_SIDE_SWEEP")
        self.assertEqual(out["pressure"],"BEARISH")

    def test_short_input_is_neutral_unknown(self):
        out=gigi_liquidity.analyze([])
        self.assertEqual(out["event"],"UNKNOWN")
        self.assertEqual(out["pressure"],"NEUTRAL")


if __name__=="__main__":
    unittest.main()
