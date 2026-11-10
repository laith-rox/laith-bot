import unittest
from v4_quick_balance import quick_message

class CautiousDisplayTests(unittest.TestCase):
    def test_explicit_eligible_candidate_shows_caution_and_reference(self):
        for score in (5, 6, 7):
            text = quick_message({"side": "BUY", "score": score,
                                  "cautious_entry": True, "delayed_reference": True})
            self.assertIn("ادخل بحذر", text)
            self.assertIn("بعد مطابقة سعر وسيطك", text)
            self.assertIn("ليس سعرًا حيًا", text)
            self.assertNotIn("صلاحية 20د", text)

    def test_score_alone_never_claims_permission(self):
        text = quick_message({"side": "SELL", "score": 7})
        self.assertNotIn("ادخل بحذر", text)
        self.assertIn("مراقبة فقط", text)
