import unittest
from v4_quote_observation import valid_quote_observation


class QuoteObservationTests(unittest.TestCase):
    def test_recent_valid(self):
        self.assertTrue(valid_quote_observation(1000, 1050))

    def test_missing_invalid(self):
        self.assertFalse(valid_quote_observation(None, 1050))

    def test_stale_invalid(self):
        self.assertFalse(valid_quote_observation(900, 1050))

    def test_future_invalid(self):
        self.assertFalse(valid_quote_observation(1100, 1050))

    def test_nan_invalid(self):
        self.assertFalse(valid_quote_observation(float("nan"), 1050))

    def test_infinity_invalid(self):
        self.assertFalse(valid_quote_observation(float("inf"), 1050))

if __name__ == "__main__":
    unittest.main()
