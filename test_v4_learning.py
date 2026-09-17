import os
import tempfile
import unittest

from storage import Store
from v4_learning import classify_trade_lesson, record_trade_lesson


class V4LearningTests(unittest.TestCase):
    def test_news_and_late_entry_are_distinguished(self):
        news = {"id": "q1", "status": "closed", "outcome": "STOP", "r": -1,
                "risk_reasons": ["خبر/حدث اقتصادي قريب"]}
        late = {"id": "q2", "status": "closed", "outcome": "STOP", "r": -1,
                "risk_reasons": ["السعر تحرك عن سعر التحليل"]}
        self.assertEqual(classify_trade_lesson(news)["reason"], "news_exposure")
        self.assertEqual(classify_trade_lesson(late)["reason"], "late_entry_price_moved")

    def test_tight_stop_and_opposing_structure_are_distinguished(self):
        tight = {"id": "o1", "status": "closed", "outcome": "STOP", "r": -1,
                 "research_v4": {"structural_risk": {"risk_atr": 0.60, "room_r": 2.0}}}
        wall = {"id": "o2", "status": "closed", "outcome": "STOP", "r": -1,
                "research_v4": {"structural_risk": {"risk_atr": 1.0, "room_r": 1.20}}}
        self.assertEqual(classify_trade_lesson(tight)["reason"], "stop_too_tight_for_structure")
        self.assertEqual(classify_trade_lesson(wall)["reason"], "opposing_structure_or_hidden_level")

    def test_journal_is_idempotent_and_summarizes_causes(self):
        trade = {"id": "q3", "status": "closed", "outcome": "STOP", "r": -1,
                 "risk_reasons": ["خبر/حدث اقتصادي قريب"]}
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "v4.db"))
            try:
                record_trade_lesson(store, trade, "quick")
                record_trade_lesson(store, trade, "quick")
                summary = store.get("v4_learning_summary")
                self.assertEqual(summary["losses"], 1)
                self.assertEqual(summary["by_reason"]["news_exposure"], 1)
                self.assertEqual(summary["by_stream"]["quick"], 1)
                self.assertEqual(summary["top_reason"], "news_exposure")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
