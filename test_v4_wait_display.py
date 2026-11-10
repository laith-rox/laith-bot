import unittest

from v4_wait_display import smart_wait_message


class V4WaitDisplayTests(unittest.TestCase):
    def test_runtime_block_is_first_and_translated(self):
        decision = {"v4": {"intelligence": {"entry_gate": {"reasons": [
            "compressed_between_support_resistance", "failed_breakout"]}}}}
        text = smart_wait_message(decision, extra_reason="degraded_reference_requires_7_of_7")
        self.assertIn("السعر الحي غير متاح", text)
        self.assertNotIn("degraded_reference", text)
        self.assertLess(text.index("السعر الحي غير متاح"), text.index("السعر محصور"))

    def test_wait_message_is_actionable_and_arabic(self):
        decision = {
            "v4": {"intelligence": {
                "preferred_side": "BUY",
                "entry_gate": {"reasons": ["compressed_between_support_resistance"]},
                "wait_plan": {"buy_trigger": 4010.0, "sell_trigger": 3990.0,
                              "confirmation": "إغلاق M15 ثم إعادة اختبار"},
                "invalidation": {"level": 3985.0, "rule": "إغلاق M15 تحت المستوى"},
                "confidence": {"score": 6.8, "label": "جيدة", "components": {
                    "trend": 10, "momentum": 6.7, "structure": 3,
                    "entry_quality": 3, "macro": 8, "volatility": 9, "data_quality": 10,
                }},
                "data_quality": {"label": "FRESH", "bar_age_seconds": 60},
            }}
        }
        text = smart_wait_message(decision, news_reason="calendar_clear", nearby=False)
        self.assertIn("السعر محصور بين دعم ومقاومة", text)
        self.assertIn("4010.00", text)
        self.assertIn("3985.00", text)
        self.assertIn("6.8/10", text)
        self.assertNotIn("compressed_between_support_resistance", text)


if __name__ == "__main__":
    unittest.main()
