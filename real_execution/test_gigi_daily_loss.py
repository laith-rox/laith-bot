import unittest
import gigi_daily_loss


class GigiDailyLossTests(unittest.TestCase):
    def test_daily_cap_is_ten_percent_of_start_equity(self):
        out=gigi_daily_loss.limits(10)
        self.assertEqual(out["daily_loss_cap_usd"],1.0)
        self.assertEqual(out["max_consecutive_losses"],3)

    def test_daily_loss_cap_stops_new_entries(self):
        out=gigi_daily_loss.validate(-1.0,2,10)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"daily_loss_cap_reached")

    def test_three_consecutive_losses_stops_new_entries(self):
        out=gigi_daily_loss.validate(-0.6,3,10)
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"],"consecutive_loss_circuit_breaker")

    def test_profit_does_not_consume_loss_budget(self):
        out=gigi_daily_loss.validate(0.5,0,10)
        self.assertTrue(out["ok"])


if __name__=="__main__":
    unittest.main()
