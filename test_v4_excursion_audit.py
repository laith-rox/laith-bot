import unittest
from datetime import datetime, timedelta, timezone
from v4_excursion_audit import audit_excursion

T = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)

def candle(i, high, low):
    return {"start": T + timedelta(minutes=5*i),
            "end": T + timedelta(minutes=5*(i+1)),
            "high": high, "low": low}

class ExcursionAuditTests(unittest.TestCase):
    def test_buy_and_sell(self):
        bars = [candle(0, 101, 99), candle(1, 104, 97)]
        buy = audit_excursion(side="BUY", entry_price=100, entry_at=T,
                              as_of=T+timedelta(minutes=10), closed_bars=bars)
        self.assertEqual((buy["mfe_price"], buy["mae_price"]), (4, 3))
        sell = audit_excursion(side="SELL", entry_price=100, entry_at=T,
                               as_of=T+timedelta(minutes=10), closed_bars=bars)
        self.assertEqual((sell["mfe_price"], sell["mae_price"]), (3, 4))
        self.assertFalse(buy["fill_assumed"])

    def test_future_and_partial_entry_candles_excluded(self):
        bars = [candle(-1, 900, 1), candle(0, 101, 99), candle(1, 900, 1)]
        result = audit_excursion(side="BUY", entry_price=100, entry_at=T,
             as_of=T+timedelta(minutes=5), closed_bars=bars)
        self.assertEqual(result["bars_used"], 1)
        self.assertEqual(result["mfe_price"], 1)

    def test_no_completed_bars(self):
        result = audit_excursion(side="BUY", entry_price=100, entry_at=T,
             as_of=T+timedelta(minutes=1), closed_bars=[candle(0, 101, 99)])
        self.assertEqual(result["status"], "insufficient_data")

    def test_bad_inputs_fail_closed(self):
        self.assertEqual(audit_excursion(side="HOLD", entry_price=100, entry_at=T,
             as_of=T, closed_bars=[])["status"], "invalid_side")
        self.assertEqual(audit_excursion(side="BUY", entry_price=100, entry_at=T,
             as_of=T+timedelta(minutes=5), closed_bars=[candle(0, 1, 9)])["status"], "invalid_data")
        self.assertEqual(audit_excursion(side="BUY", entry_price=100, entry_at=T,
             as_of=T-timedelta(minutes=5), closed_bars=[])["status"], "invalid_data")

if __name__ == "__main__":
    unittest.main()
