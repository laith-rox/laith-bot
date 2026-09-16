import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from v3_research import analyze_v3, session_label

UTC = timezone.utc


class V3ResearchTests(unittest.TestCase):
    def test_forced_bias_is_rejected_as_trade_candidate(self):
        base = {"side": "BUY", "forced": True, "reason": "best_available_bias"}
        with patch("v3_research.analyze", return_value=base), \
             patch("v3_research.session_label", return_value="LONDON"), \
             patch("v3_research.volatility_regime", return_value={"label": "NORMAL", "percentile": 50.0, "atr": 2.0}):
            result = analyze_v3([], datetime(2026, 9, 16, 12, tzinfo=UTC))
        self.assertEqual(result["side"], "WAIT")
        self.assertEqual(result["reason"], "v3_forced_bias_rejected")
        self.assertTrue(result["v3"]["research_only"])

    def test_extreme_volatility_vetoes_otherwise_strict_signal(self):
        base = {"side": "SELL", "forced": False, "reason": "entry_conditions_met"}
        with patch("v3_research.analyze", return_value=base), \
             patch("v3_research.session_label", return_value="NEW_YORK"), \
             patch("v3_research.volatility_regime", return_value={"label": "EXTREME", "percentile": 98.0, "atr": 8.0}):
            result = analyze_v3([], datetime(2026, 9, 16, 15, tzinfo=UTC))
        self.assertEqual(result["side"], "WAIT")
        self.assertEqual(result["reason"], "v3_extreme_volatility")

    def test_core_session_normal_vol_keeps_strict_signal(self):
        base = {"side": "BUY", "forced": False, "reason": "entry_conditions_met"}
        with patch("v3_research.analyze", return_value=base), \
             patch("v3_research.session_label", return_value="LONDON_NEW_YORK_OVERLAP"), \
             patch("v3_research.volatility_regime", return_value={"label": "NORMAL", "percentile": 55.0, "atr": 3.0}):
            result = analyze_v3([], datetime(2026, 9, 16, 14, tzinfo=UTC))
        self.assertEqual(result["side"], "BUY")
        self.assertEqual(result["reason"], "entry_conditions_met")

    def test_session_labels_are_dst_aware(self):
        self.assertEqual(session_label(datetime(2026, 9, 16, 1, tzinfo=UTC)), "ASIA")
        self.assertEqual(session_label(datetime(2026, 9, 16, 8, tzinfo=UTC)), "LONDON")
        self.assertEqual(session_label(datetime(2026, 9, 16, 13, tzinfo=UTC)), "LONDON_NEW_YORK_OVERLAP")


if __name__ == "__main__":
    unittest.main()
