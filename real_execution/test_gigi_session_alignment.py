import inspect
import unittest

import adaptive_sniper_engine
import real_analysis_engine


class GigiSessionAlignmentTests(unittest.TestCase):
    def test_compute_signal_sniper_window_is_05_to_20(self):
        source = inspect.getsource(real_analysis_engine.compute_signal)
        self.assertIn("sniper_window = 5*60 <= minute_local < 20*60", source)
        self.assertNotIn("night_sniper =", source)

    def test_adaptive_main_clock_starts_at_five(self):
        source = inspect.getsource(adaptive_sniper_engine.decide)
        self.assertIn("day_main = 5 <= hour_local < 20", source)


if __name__ == "__main__":
    unittest.main()
