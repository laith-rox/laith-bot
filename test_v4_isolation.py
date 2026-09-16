from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from v4_experiment import V4_EXPERIMENT, experiment_id
from v4_research import analyze_v4

UTC = timezone.utc


class V4IsolationTests(unittest.TestCase):
    def test_v4_identity_is_paper_only_and_separate_db(self):
        self.assertEqual(V4_EXPERIMENT["generation"], "V4")
        self.assertEqual(V4_EXPERIMENT["mode"], "paper_only")
        self.assertEqual(V4_EXPERIMENT["isolation"]["database"], "/data/laith_v4.db")
        self.assertFalse(V4_EXPERIMENT["isolation"]["telegram"])
        self.assertFalse(V4_EXPERIMENT["isolation"]["broker_orders"])
        self.assertEqual(len(experiment_id()), 16)

    def test_v4_rebrands_v3_contract_without_changing_trade_decision(self):
        base = {
            "side": "WAIT",
            "reason": "v3_forced_bias_rejected",
            "v3": {"session": "LONDON", "research_only": True},
        }
        with patch("v4_research.analyze_v3", return_value=base):
            result = analyze_v4([], datetime(2026, 9, 16, 12, tzinfo=UTC))
        self.assertNotIn("v3", result)
        self.assertEqual(result["reason"], "v4_forced_bias_rejected")
        self.assertEqual(result["v4"]["generation"], "V4")
        self.assertTrue(result["v4"]["paper_only"])
        self.assertEqual(result["side"], "WAIT")


if __name__ == "__main__":
    unittest.main()
