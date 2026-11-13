import unittest
from safety_monitor import warning_message


class CompactEmergencyTests(unittest.TestCase):
    def test_correction_short_message(self):
        trade = {"side": "SELL", "stop": 3875.44}
        event = {"kind": "correction", "price": 3874.89, "stamp": 1794602820, "pressure_checks": [True, True, True, False]}
        msg = warning_message(trade, event)
        self.assertIn("3/4", msg)
        self.assertIn("75%", msg)
        self.assertIn("3875.44", msg)
        self.assertIn("صعود محتمل", msg)
        self.assertNotIn("ليس سعر وسيطك", msg)
        self.assertNotIn("لا إغلاق آلي", msg)

    def test_missing_pressure_is_not_invented(self):
        trade = {"side": "BUY", "stop": 3870.0}
        event = {"kind": "correction", "price": 3874.89, "stamp": 1794602820}
        msg = warning_message(trade, event)
        self.assertIn("غير متاح", msg)
        self.assertIn("هبوط محتمل", msg)


if __name__ == "__main__":
    unittest.main()
