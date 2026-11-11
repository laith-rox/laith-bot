import unittest
from v4_telegram import continuation_message


class V4ContinuationMessageTests(unittest.TestCase):
    def snapshot(self, side, direction=None, strength=None):
        return dict(side=side, state="متوسطة", score=5, stop=4047.77,
                    price=4062.50, entry=4056.14, tp1=4066.89, tp2=4071.68,
                    correction_direction=direction, correction_strength=strength)

    def test_buy_side_visible(self):
        message = continuation_message(self.snapshot("BUY", "UP", "MEDIUM"))
        self.assertIn("شراء 🟢⬆️", message)
        self.assertIn("صاعد / متوسط", message)

    def test_sell_side_visible(self):
        self.assertIn("بيع 🔴⬇️", continuation_message(self.snapshot("SELL")))

    def test_missing_correction_is_arabic(self):
        message = continuation_message(self.snapshot("BUY", None, "UNAVAILABLE"))
        self.assertIn("التصحيح: غير متاح / غير متاح", message)
        self.assertNotIn("None", message)
        self.assertNotIn("UNAVAILABLE", message)

    def test_unknown_side_does_not_guess(self):
        self.assertIn("اتجاه غير متاح", continuation_message(self.snapshot(None)))


if __name__ == "__main__":
    unittest.main()
