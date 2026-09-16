from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from v3_global_data import (
    Observation, asof_pair, build_snapshot, gold_macro_score, macro_alignment,
    parse_fred_csv, parse_fred_bundle,
)
from v3_metrics import max_drawdown, summarize_r
from v3_research import analyze_v3, research_gate, session_label

UTC = timezone.utc


def macro(score):
    return {"gold_macro_score": score, "coverage": 4, "primary_coverage": 2}


class GlobalDataTests(unittest.TestCase):
    def test_fred_parser_and_asof_rule_exclude_same_day(self):
        text = "DATE,DGS10\n2026-09-14,4.10\n2026-09-15,4.20\n2026-09-16,4.30\n"
        rows = parse_fred_csv(text, "DGS10")
        pair = asof_pair(rows, datetime(2026, 9, 16, 15, tzinfo=UTC), lag=1)
        self.assertEqual(pair[0].day.isoformat(), "2026-09-15")
        self.assertEqual(pair[0].value, 4.20)
        self.assertEqual(pair[1].value, 4.10)

    def test_bundle_parser_keeps_available_series(self):
        text = "DATE,DTWEXBGS,DGS10,DFII10\n2026-09-14,100,4.10,1.80\n2026-09-15,99,4.20,1.75\n"
        history = parse_fred_bundle(text)
        self.assertEqual(history["usd_broad"][-1].value, 99)
        self.assertEqual(history["nominal_10y"][-1].value, 4.20)
        self.assertEqual(history["real_10y"][-1].value, 1.75)
        self.assertNotIn("vix", history)

    def test_macro_score_direction_is_symmetric(self):
        supportive = {"usd_broad": -1, "real_10y": -0.2, "nominal_10y": -0.1, "vix": 2, "oil_wti": 5}
        score, parts = gold_macro_score(supportive)
        self.assertEqual(score, 6)
        self.assertEqual(parts["oil_wti"], 0)
        self.assertEqual(macro_alignment("BUY", macro(score)), "STRONG_ALIGN")
        self.assertEqual(macro_alignment("SELL", macro(score)), "STRONG_CONFLICT")

    def test_macro_alignment_requires_coverage(self):
        self.assertEqual(
            macro_alignment("BUY", {"gold_macro_score": 6, "coverage": 2, "primary_coverage": 1}),
            "UNAVAILABLE",
        )

    def test_snapshot_uses_only_prior_observations(self):
        history = {
            "usd_broad": [Observation(datetime(2026, 9, 14).date(), 100), Observation(datetime(2026, 9, 15).date(), 99)],
            "real_10y": [Observation(datetime(2026, 9, 14).date(), 2.0), Observation(datetime(2026, 9, 15).date(), 1.8)],
            "nominal_10y": [Observation(datetime(2026, 9, 14).date(), 4.0), Observation(datetime(2026, 9, 15).date(), 3.9)],
            "vix": [Observation(datetime(2026, 9, 14).date(), 15), Observation(datetime(2026, 9, 15).date(), 18)],
            "oil_wti": [Observation(datetime(2026, 9, 14).date(), 100), Observation(datetime(2026, 9, 15).date(), 101)],
        }
        snap = build_snapshot(history, datetime(2026, 9, 16, 12, tzinfo=UTC))
        self.assertEqual(snap["values"]["usd_broad"], 99)
        self.assertEqual(snap["coverage"], 5)
        self.assertEqual(snap["primary_coverage"], 2)
        self.assertGreater(snap["gold_macro_score"], 0)


class GateTests(unittest.TestCase):
    def base(self, side="BUY"):
        return {"side": side, "forced": False, "reason": "entry_conditions_met"}

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

    def test_only_strong_macro_conflict_vetoes(self):
        strong = macro(-6)
        mild = macro(-2)
        self.assertEqual(research_gate(self.base("BUY"), "LONDON", {"label": "NORMAL"}, strong), "v3_strong_macro_conflict")
        self.assertIsNone(research_gate(self.base("BUY"), "LONDON", {"label": "NORMAL"}, mild))

    def test_core_session_normal_vol_keeps_strict_signal(self):
        base = {"side": "BUY", "forced": False, "reason": "entry_conditions_met"}
        with patch("v3_research.analyze", return_value=base), \
             patch("v3_research.session_label", return_value="LONDON_NEW_YORK_OVERLAP"), \
             patch("v3_research.volatility_regime", return_value={"label": "NORMAL", "percentile": 55.0, "atr": 3.0}):
            result = analyze_v3([], datetime(2026, 9, 16, 14, tzinfo=UTC), macro=macro(2))
        self.assertEqual(result["side"], "BUY")
        self.assertEqual(result["reason"], "entry_conditions_met")
        self.assertEqual(result["v3"]["macro_alignment"], "ALIGN")

    def test_session_labels_are_dst_aware(self):
        self.assertEqual(session_label(datetime(2026, 9, 16, 1, tzinfo=UTC)), "ASIA")
        self.assertEqual(session_label(datetime(2026, 9, 16, 8, tzinfo=UTC)), "LONDON")
        self.assertEqual(session_label(datetime(2026, 9, 16, 13, tzinfo=UTC)), "LONDON_NEW_YORK_OVERLAP")
        self.assertEqual(session_label(datetime(2026, 1, 15, 14, tzinfo=UTC)), "LONDON_NEW_YORK_OVERLAP")


class MetricsTests(unittest.TestCase):
    def test_drawdown_and_summary(self):
        values = [1, -1, -1, 2, -0.5]
        self.assertEqual(max_drawdown(values), 2)
        result = summarize_r(values)
        self.assertEqual(result["measured"], 5)
        self.assertEqual(result["wins"], 2)
        self.assertEqual(result["losses"], 3)
        self.assertEqual(result["longest_loss_streak"], 2)


if __name__ == "__main__":
    unittest.main()
