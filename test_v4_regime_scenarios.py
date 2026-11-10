import unittest
from v4_regime_scenarios import analyze_regime, scenario_hypotheses

class RegimeTests(unittest.TestCase):
    def test_uptrend(self):
        bars = [{"high": 4001 + i, "low": 3999 + i, "close": 4000 + i} for i in range(40)]
        result = analyze_regime(bars)
        self.assertEqual(result["regime"], "UPTREND")
        scenarios = scenario_hypotheses(result, support=4000, resistance=4045, last_price=4040)
        self.assertEqual(len(scenarios), 3)
        self.assertTrue(scenarios[0]["preferred"])

    def test_range(self):
        bars = [{"high": 4002 + i % 2, "low": 3998 + i % 2,
                 "close": 4000 + i % 2} for i in range(40)]
        self.assertEqual(analyze_regime(bars)["regime"], "RANGE")

    def test_invalid_and_insufficient(self):
        self.assertEqual(analyze_regime([])["regime"], "UNKNOWN")
        bars = [{"high": 3999, "low": 4001, "close": 4000} for _ in range(40)]
        self.assertFalse(analyze_regime(bars)["actionable"])
        self.assertEqual(scenario_hypotheses({"regime": "UPTREND"}, support=5,
                                              resistance=4, last_price=4.5), ())

if __name__ == '__main__':
    unittest.main()
